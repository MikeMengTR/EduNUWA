// Web Audio API wrapper: preload, play, pause, rate control, analyser for LipSync
export class AudioPlayer {
  private _audioCtx: AudioContext | null = null;
  private _analyser: AnalyserNode | null = null;
  private _gainNode: GainNode | null = null;
  private _buffers = new Map<string, AudioBuffer | null>();
  private _currentSource: AudioBufferSourceNode | null = null;
  private _currentEventId: string | null = null;
  private _startTime = 0;
  private _pauseOffset = 0;
  private _isPlaying = false;
  private _rate = 1.0;
  // 流式播放状态（StreamingPlayer 用，与静态 play/preload 独立，互不影响）
  private _streamBuffer: AudioBuffer | null = null;
  private _streamOnEnded: (() => void) | null = null;
  private _streamSuppress = false;
  private _streamNullTimer: number | null = null;

  private _getCtx(): AudioContext {
    if (!this._audioCtx) {
      this._audioCtx = new AudioContext();
      this._analyser = this._audioCtx.createAnalyser();
      this._analyser.fftSize = 256;
      this._gainNode = this._audioCtx.createGain();
      this._gainNode.gain.value = 1.0;
      this._analyser.connect(this._gainNode);
      this._gainNode.connect(this._audioCtx.destination);
    }
    return this._audioCtx;
  }

  getAnalyserNode(): AnalyserNode {
    this._getCtx();
    return this._analyser!;
  }

  async preload(eventId: string, url: string): Promise<void> {
    if (!url) {
      this._buffers.set(eventId, null);
      return;
    }
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const arrayBuf = await resp.arrayBuffer();
      const audioCtx = this._getCtx();
      const audioBuf = await audioCtx.decodeAudioData(arrayBuf);
      this._buffers.set(eventId, audioBuf);
    } catch (e) {
      console.warn(`[AudioPlayer] Preload failed for ${eventId}: ${e}`);
      this._buffers.set(eventId, null);
    }
  }

  play(eventId: string): void {
    this.stop();
    const buffer = this._buffers.get(eventId);
    this._currentEventId = eventId;

    if (!buffer) {
      this._isPlaying = true;
      this._startTime = this._getCtx().currentTime;
      this._pauseOffset = 0;
      return;
    }

    const audioCtx = this._getCtx();
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }

    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.playbackRate.value = this._rate;

    source.connect(this._analyser!);

    source.start(0, this._pauseOffset);
    this._startTime = audioCtx.currentTime - this._pauseOffset / this._rate;
    this._currentSource = source;
    this._isPlaying = true;

    source.onended = () => {
      if (this._currentSource === source) {
        this._isPlaying = false;
        this._currentSource = null;
      }
    };
  }

  pause(): void {
    if (!this._isPlaying) return;
    this._pauseOffset = this.getElapsed();
    this.stopSource();
    this._isPlaying = false;
  }

  resume(): void {
    if (this._isPlaying || !this._currentEventId) return;
    this.play(this._currentEventId);
  }

  stop(): void {
    this.stopSource();
    this._pauseOffset = 0;
    this._isPlaying = false;
    this._currentEventId = null;
  }

  private stopSource(): void {
    if (this._currentSource) {
      try { this._currentSource.stop(); } catch (_) { /* already stopped */ }
      this._currentSource.disconnect();
      this._currentSource = null;
    }
  }

  setPlaybackRate(rate: number): void {
    this._rate = rate;
    if (this._currentSource) {
      this._currentSource.playbackRate.value = rate;
    }
  }

  getElapsed(): number {
    if (!this._isPlaying) return this._pauseOffset;
    if (!this._currentSource && this._buffers.get(this._currentEventId || '') === null) {
      return this._pauseOffset + (performance.now() / 1000 - this._startTime) * this._rate;
    }
    const ctx = this._audioCtx;
    if (!ctx) return this._pauseOffset;
    return (ctx.currentTime - this._startTime) * this._rate;
  }

  get isPlaying(): boolean {
    return this._isPlaying;
  }

  // --- 流式播放接口（StreamingPlayer 专用）---

  /** 解码 TTS 返回的音频字节为 AudioBuffer */
  async decode(arrayBuffer: ArrayBuffer): Promise<AudioBuffer> {
    return this._getCtx().decodeAudioData(arrayBuffer);
  }

  /** 播放任意 buffer；自然结束时调 onEnded。buffer 为 null（合成失败）时兜底等待后触发 onEnded。 */
  playBuffer(buffer: AudioBuffer | null, onEnded: () => void): void {
    this.stopSource();
    if (this._streamNullTimer) { clearTimeout(this._streamNullTimer); this._streamNullTimer = null; }
    this._streamBuffer = buffer;
    this._streamOnEnded = onEnded;
    this._streamSuppress = false;

    const ctx = this._getCtx();
    if (ctx.state === 'suspended') ctx.resume();

    if (!buffer) {
      // 无音频兜底：等 2s 后视作念完，字幕已显示，不卡死
      this._isPlaying = true;
      this._streamNullTimer = window.setTimeout(() => {
        this._isPlaying = false;
        if (!this._streamSuppress && this._streamOnEnded) this._streamOnEnded();
      }, 2000);
      return;
    }

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.playbackRate.value = this._rate;
    source.connect(this._analyser!);
    source.start(0);
    this._currentSource = source;
    this._isPlaying = true;
    source.onended = () => {
      if (this._currentSource === source) {
        this._currentSource = null;
        this._isPlaying = false;
        if (!this._streamSuppress && this._streamOnEnded) this._streamOnEnded();
      }
    };
  }

  /** 流式暂停：停止当前句但不触发 onEnded（不推进队列） */
  pauseStream(): void {
    this._streamSuppress = true;
    if (this._streamNullTimer) { clearTimeout(this._streamNullTimer); this._streamNullTimer = null; }
    this.stopSource();
    this._isPlaying = false;
  }

  /** 流式恢复：从当前句开头重播 */
  resumeStream(): void {
    if (this._isPlaying || !this._streamOnEnded) return;
    this.playBuffer(this._streamBuffer, this._streamOnEnded);
  }

  destroy(): void {
    if (this._streamNullTimer) { clearTimeout(this._streamNullTimer); this._streamNullTimer = null; }
    this.stop();
    this._buffers.clear();
    if (this._gainNode) { this._gainNode.disconnect(); this._gainNode = null; }
    if (this._analyser) { this._analyser.disconnect(); this._analyser = null; }
    if (this._audioCtx) { this._audioCtx.close(); this._audioCtx = null; }
  }
}
