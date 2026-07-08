// 流式顺序播放控制器：逐句请求 TTS（老师音色）边合成边播。合成是「持续流水线」式
// 提前进行——始终保持最多 _synthCap 条未就绪小句在合成队列里（_synthAhead），每合成完
// 一条立刻喂下一条，不等当前句/事件播完，掩盖合成延迟、不让后端空转。与静态 Player 同
// 接口（play/pause/setSpeed/on/destroy/getAnalyserNode），不依赖绝对时间线。
// 销毁时 abort 所有在途请求、停止继续生成。
import { AudioPlayer } from './AudioPlayer';
import type { PlayerEventName, PlayerEventHandler, PlayerEvent } from './types';

export interface StreamEvent {
  seq: number;
  type: 'speak' | 'board' | 'formula' | 'table' | 'image' | 'pause';
  text?: string;
  // 后端对长 speak 切出的小句数组：仅供音频层逐句流式合成+播放；
  // 字幕仍用整句 text 显示，不被切碎。无此字段时退化为整句一次合成。
  segments?: string[];
  action?: string;
  content?: string | string[];
  latex?: string;
  display_mode?: boolean | string;
  duration_sec?: number;
  title?: string;
  columns?: string[];
  rows?: string[][];
  src?: string;
  caption?: string;
  media_type?: string;
  image_id?: string;
}

type State = 'idle' | 'playing' | 'waiting' | 'paused' | 'ended' | 'destroyed';

// 板书/公式/表格渲染后立即推进下一事件（仅留极短间隔做级联淡入），
// 不再每条板书各等 2s——让连续板书快速成片，时间线由语音主导。
const BOARD_FLOW_MS = 140;

// 逐句音频之间留出极短自然停顿，避免「贴脸连读 / 像被打断」（句末尾音被即时盖掉）。
// 注意：句间切换本身（onended 回调 + setTimeout 调度 + 下一句 await/createBufferSource 起播）
// 已有几十 ms 的固有开销（内存卡顿时放大），所以「实际听感停顿 = 这里的 gap + 切换固有开销」。
// 因此 gap 只需很小——当作在固有切换间隔之上「再补一点点」换气空间，切勿设大。
const SEGMENT_GAP_MS = 30;    // 同一 speak 内、相邻小句之间（逗号/顿点处）
const SENTENCE_GAP_MS = 70;   // speak 整句之间（句末停顿，给尾音+换气留空间）

export class StreamingPlayer {
  private _events: StreamEvent[];
  private _teacherId: string;
  private _apiBase: string;
  private _token: string;
  private _audio = new AudioPlayer();
  // 音频缓存/在途请求按【文本】为键：长 speak 的各小句各自独立缓存与去重，
  // 同样的句子（如重复预取）只合成一次。
  private _cache = new Map<string, AudioBuffer | null>();
  private _pending = new Map<string, Promise<void>>();
  private _idx = 0;
  private _state: State = 'idle';
  private _timer: number | null = null;
  private _listeners = new Map<PlayerEventName, Set<PlayerEventHandler>>();
  // live 模式（SSE push）：事件边生成边 appendEvents 进来，endOfStream 前
  // 缓冲耗尽只是 waiting 不是结束
  private _eos: boolean;
  private _endEmitted = false;
  private _seenSeqs = new Set<number>();
  private _pausedFromWaiting = false;
  // 提前合成的 lookahead 窗口：始终让最多这么多条「未就绪」小句在合成流水线里排队，
  // 不等当前句/事件播完。后端 TTS 串行(单 GPU)，持续喂满让它不空转。
  private _synthCap = 3;
  // 销毁/退出时中止所有在途 TTS 请求——不再继续生成（配合切老师卸载 iframe）
  private _abort = new AbortController();
  // 当前倍速：句间停顿按倍速等比缩放，保证不同语速下停顿观感一致
  private _rate = 1.0;

  constructor(events: StreamEvent[], teacherId: string, apiBase: string, token: string,
              opts?: { live?: boolean }) {
    this._events = [...events].sort((a, b) => a.seq - b.seq);
    this._events.forEach(e => this._seenSeqs.add(e.seq));
    this._teacherId = teacherId;
    this._apiBase = apiBase.replace(/\/$/, '');
    this._token = token;
    this._eos = !opts?.live; // 非 live：构造时事件已齐，播完即结束（兼容原行为）
  }

  /** live 模式：追加上游推来的新事件（按 seq 去重，重复推送安全） */
  appendEvents(events: StreamEvent[]): void {
    if (this._state === 'destroyed' || this._state === 'ended') return;
    const fresh = events.filter(e => !this._seenSeqs.has(e.seq));
    if (!fresh.length) return;
    fresh.forEach(e => this._seenSeqs.add(e.seq));
    this._events.push(...fresh);
    if (this._state === 'waiting') {
      this._state = 'playing';
      this._emit('resumed', {});
      this._playNext();
    } else if (this._state === 'playing') {
      this._synthAhead(); // 追加了新事件：继续把合成流水线喂满
    }
  }

  /** live 模式：上游声明不再有新事件 */
  endOfStream(): void {
    this._eos = true;
    if (this._state === 'waiting' && this._idx >= this._events.length) {
      this._finish();
    }
  }

  getAnalyserNode(): AnalyserNode {
    return this._audio.getAnalyserNode();
  }

  on(event: PlayerEventName, cb: PlayerEventHandler): void {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event)!.add(cb);
  }

  play(): void {
    if (this._state === 'destroyed' || this._state === 'ended') return;
    const ctx = this._audio.getAnalyserNode().context as AudioContext;
    if (ctx.state === 'suspended') ctx.resume();
    if (this._state === 'paused') {
      this._state = 'playing';
      if (this._pausedFromWaiting) {
        // waiting 中被暂停：没有挂起的音频/定时器，重新进推进循环
        // （_playNext 会按当前缓冲情况回到 waiting 或继续播）
        this._pausedFromWaiting = false;
        this._playNext();
      } else {
        this._audio.resumeStream();
      }
      return;
    }
    if (this._state === 'playing' || this._state === 'waiting') return;
    this._state = 'playing';
    this._idx = 0;
    this._playNext();
  }

  pause(): void {
    if (this._state !== 'playing' && this._state !== 'waiting') return;
    this._pausedFromWaiting = this._state === 'waiting';
    this._state = 'paused';
    this._audio.pauseStream();
    if (this._timer) { clearTimeout(this._timer); this._timer = null; }
  }

  setSpeed(rate: number): void {
    this._rate = rate > 0 ? rate : 1.0;
    this._audio.setPlaybackRate(rate);
  }

  destroy(): void {
    this._state = 'destroyed';
    try { this._abort.abort(); } catch { /* noop */ }  // 退出/切老师：中止在途 TTS、停止继续生成
    if (this._timer) { clearTimeout(this._timer); this._timer = null; }
    this._audio.destroy();
    this._listeners.clear();
  }

  // --- 内部 ---

  private async _playNext(): Promise<void> {
    if (this._state !== 'playing') return;
    if (this._idx >= this._events.length) {
      if (this._eos) {
        this._finish();
      } else {
        // live 模式：缓冲耗尽但上游还在生成，等 appendEvents 唤醒
        this._state = 'waiting';
        this._emit('waiting', {});
      }
      return;
    }
    const evt = this._events[this._idx];
    const eventId = `evt_${String(evt.seq).padStart(4, '0')}`;
    const item = this._toTimelineItem(evt, eventId);

    if (evt.type === 'speak') {
      // 字幕按整句显示一次（不随音频小句切碎）
      this._emit('timeline:item', item);
      this._emit('audio:start', { event_id: eventId, text: evt.text });
      // 音频层：有 segments 则逐小句流式，否则整句一次合成
      const segs = (evt.segments && evt.segments.length) ? evt.segments : [evt.text || ''];
      void this._playSegments(segs, 0, eventId);
    } else if (evt.type === 'board' || evt.type === 'formula' || evt.type === 'table') {
      this._emit('timeline:item', item);
      this._synthAhead();
      // 板书不阻塞：渲染即推进，连续板书快速级联出现（不再每条等 duration_sec）
      this._timer = window.setTimeout(() => this._advance(), BOARD_FLOW_MS);
    } else if (evt.type === 'image') {
      this._emit('timeline:item', item);
      this._synthAhead();
      const dwell = (evt.duration_sec || 3.0) * 1000; // 给学生留看图时间
      this._timer = window.setTimeout(() => this._advance(), dwell);
    } else if (evt.type === 'pause') {
      const dwell = (evt.duration_sec || 1.5) * 1000;
      this._timer = window.setTimeout(() => this._advance(), dwell);
    } else {
      this._advance();
    }
  }

  /** 在同一条 speak 字幕下，逐小句合成+播放；播完最后一小句再 advance 到下一事件。
   *  播每一小句时预取本句的下一小句（最后一小句则预取下一个 speak 事件的首句），
   *  使"边合成边播"延伸到小句粒度——长段落首音 = 第一小句合成时间，而非整段。*/
  private async _playSegments(segs: string[], i: number, eventId: string): Promise<void> {
    if (this._state !== 'playing') return;
    if (i >= segs.length) {
      this._emit('audio:end', { event_id: eventId });
      this._advance();
      return;
    }
    this._synthAhead();                       // 进入即把后续若干小句铺进合成流水线（不等播完）
    const buf = await this._ensureAudioForText(segs[i]);
    if (this._state !== 'playing') return; // await 期间可能被暂停/销毁
    this._synthAhead();                       // 本句已就绪：窗口前移，继续往后铺
    if (!buf) { void this._playSegments(segs, i + 1, eventId); return; } // 静音/失败跳过该小句
    this._audio.playBuffer(buf, () => {
      // 本句播完后留一段极短停顿再接下一句：小句间(逗号处)短、整句末尾稍长，
      // 给尾音+换气留空间，避免「贴脸连读 / 像被打断」。停顿随倍速等比缩放。
      const isLast = i + 1 >= segs.length;
      const gap = (isLast ? SENTENCE_GAP_MS : SEGMENT_GAP_MS) / this._rate;
      this._timer = window.setTimeout(() => {
        if (this._state !== 'playing') return;   // 停顿期间被暂停/销毁则不推进
        void this._playSegments(segs, i + 1, eventId);
      }, gap);
    });
  }

  private _advance(): void {
    if (this._state !== 'playing') return;
    this._idx++;
    this._playNext();
  }

  private _finish(): void {
    this._state = 'ended';
    if (!this._endEmitted) {
      this._endEmitted = true;
      this._emit('end', {});
    }
  }

  /** 规范化为 App 的 timeline:item 期望结构（formula display_mode 转 block/inline，与静态一致） */
  private _toTimelineItem(evt: StreamEvent, eventId: string): any {
    const base: any = { ...evt, event_id: eventId };
    if (evt.type === 'formula') {
      base.display_mode = evt.display_mode ? 'block' : 'inline';
    }
    return base;
  }

  /** 确保某段【文本】的音频已就绪（按文本去重：cache 命中直接返回，pending 则等待，否则发起请求） */
  private async _ensureAudioForText(text: string): Promise<AudioBuffer | null> {
    const key = (text || '').trim();
    if (!key) return null;
    if (this._cache.has(key)) return this._cache.get(key) ?? null;
    if (this._pending.has(key)) {
      await this._pending.get(key);
      return this._cache.get(key) ?? null;
    }
    const p = this._fetchTTS(key).then((buf) => {
      this._cache.set(key, buf);
      this._pending.delete(key);
    });
    this._pending.set(key, p);
    await p;
    return this._cache.get(key) ?? null;
  }

  /** 持续提前合成：从当前事件起，确保接下来最多 _synthCap 条「未就绪」小句一直在合成
   *  流水线里（pending 或即将发起），每合成完一条就再喂下一条——不等当前句/事件播完。
   *  后端 TTS 串行(单 GPU)，这些请求在后端排队，前端按文本缓存，播放时直接取用。 */
  private _synthAhead(): void {
    if (this._state === 'destroyed' || this._state === 'ended') return;
    let inflight = 0;
    for (let i = this._idx; i < this._events.length; i++) {
      const e = this._events[i];
      if (e.type !== 'speak') continue;
      const segs = (e.segments && e.segments.length) ? e.segments : [e.text || ''];
      for (const s of segs) {
        const key = (s || '').trim();
        if (!key || this._cache.has(key)) continue;   // 空 / 已就绪：不占名额
        inflight++;
        if (!this._pending.has(key)) {
          void this._ensureAudioForText(key).then(() => this._synthAhead());
        }
        if (inflight >= this._synthCap) return;        // lookahead 窗口已铺满
      }
    }
  }

  private async _fetchTTS(text: string): Promise<AudioBuffer | null> {
    if (!text.trim()) return null;
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (this._token) headers['Authorization'] = `Bearer ${this._token}`;
      const resp = await fetch(`${this._apiBase}/tts`, {
        method: 'POST', headers,
        body: JSON.stringify({ text, teacher_id: this._teacherId }),
        signal: this._abort.signal,
      });
      if (!resp.ok) { console.warn(`[StreamingPlayer] TTS HTTP ${resp.status}`); return null; }
      const ab = await resp.arrayBuffer();
      return await this._audio.decode(ab);
    } catch (e) {
      console.warn('[StreamingPlayer] TTS fetch/decode failed:', e);
      return null;
    }
  }

  private _emit(type: PlayerEventName, data?: any): void {
    const handlers = this._listeners.get(type);
    if (!handlers) return;
    const event: PlayerEvent = { type, data };
    handlers.forEach((cb) => cb(event));
  }
}
