// App orchestrator — loads events/playback, creates Player, 自动播放 + 暂停/继续
import { useState, useRef, useEffect, useCallback } from 'react';
import { Player } from './player_runtime/Player';
import { StreamingPlayer } from './player_runtime/StreamingPlayer';
import { LipSync } from './live2d_frontend/LipSync';
import { Blackboard, applyBoardAction } from './blackboard_frontend/Blackboard';
import { Live2DStage } from './live2d_frontend/Live2DStage';
import type {
  PlaybackData, TimelineItem, FormulaItem, TableItem, ImageItem,
} from './player_runtime/types';
import type { BoardStateItem } from './blackboard_frontend/types';
import './App.css';

// 从 URL 参数获取播放数据路径和鉴权 token
const params = new URLSearchParams(window.location.search);
const PLAYBACK_URL = params.get('playback') || '/data/sessions/SES_20260601_001/playback_data.json';
const EVENTS_URL = params.get('events') || '';
const TEACHER_ID = params.get('teacherId') || '';
const STREAM_MODE = params.get('stream') === '1' || !!EVENTS_URL;
// push 模式：events 由父页面经 postMessage 增量推入（LLM 边生成边播），不 fetch
const PUSH_MODE = params.get('push') === '1';
const PUSH_SESSION = params.get('session') || '';
const AUTH_TOKEN = params.get('token') || '';
const API_BASE = params.get('apiBase') || '/api/v1';
const AVATAR_URL = params.get('avatar') ? decodeURIComponent(params.get('avatar')!) : '';
const AVATAR_URL_ALT = params.get('avatarAlt') ? decodeURIComponent(params.get('avatarAlt')!) : '';
const TEACHER_NAME = params.get('teacherName') ? decodeURIComponent(params.get('teacherName')!) : 'Teacher';
// hostAvatar=1：父页（M6 虚拟教室）接管数字人渲染（可拖动/可隐藏），本页不画头像，
// 仅把口型「张/合」状态经 postMessage 回传父页驱动动画。其它消费者（课程播放器/直开）不带此参数，照旧本地渲染。
const HOST_AVATAR = params.get('hostAvatar') === '1';
// renderOnly=1：历史回看的纯板书静态模式。读 events.json 后把所有 board/formula/table/image
// 事件一次性归约成「板书放完后的最终状态」直接铺到黑板，不创建播放器、不发 TTS、不放音频。
// 学生在虚拟课堂点过去某节课的「回看板书」时用（events= 指向那节课 sessions/{sid}/events.json）。
const RENDER_ONLY = params.get('renderOnly') === '1';

export function App() {
  const [loaded, setLoaded] = useState(false);
  const [boardItems, setBoardItems] = useState<BoardStateItem[]>([]);
  // 当前活跃板书组：随事件流推进，该组板书放大显示以聚焦注意力，旧组缩回正常字号。
  const [activeGroupId, setActiveGroupId] = useState(0);
  const [currentText, setCurrentText] = useState('');
  const [mouthOpen, setMouthOpen] = useState(0);
  const [statusText, setStatusText] = useState('准备讲解…');
  const [isPlaying, setIsPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const playerRef = useRef<Player | StreamingPlayer | null>(null);
  const lipSyncRef = useRef<LipSync | null>(null);
  // 聚焦分组状态：groupCounter 递增的组号；speakSinceBoard 标记「上次写板书之后是否讲过话」
  // ——讲过话再写新板书 → 开新组（旧组缩回、新组放大）；连续写板书不讲话 → 仍属同一组。
  const groupCounterRef = useRef(0);
  const speakSinceBoardRef = useRef(false);

  useEffect(() => {
    let removeMessageListener: (() => void) | null = null;

    const init = async () => {
      try {
        const fetchHeaders: Record<string, string> = {};
        if (AUTH_TOKEN) fetchHeaders['Authorization'] = `Bearer ${AUTH_TOKEN}`;

        // 历史回看：纯板书静态模式——读 events.json，把板书类事件归约成最终态直接铺上黑板。
        // 不创建任何 Player/LipSync，不发 TTS（_advance/_fetchTTS 全不走），首屏即终态。
        if (RENDER_ONLY) {
          const url = EVENTS_URL || PLAYBACK_URL;
          const resp = await fetch(url, { headers: fetchHeaders });
          if (!resp.ok) throw new Error(`HTTP ${resp.status} - ${resp.statusText}`);
          const ed = await resp.json();
          const events = ed.events || [];
          let state: BoardStateItem[] = [];
          for (const e of events) {
            const eventId = `evt_${String(e.seq ?? state.length).padStart(4, '0')}`;
            if (e.type === 'board') {
              state = applyBoardAction(state, {
                eventId, action: e.action, content: e.content, highlighted: false, timestamp: e.seq ?? 0,
              });
            } else if (e.type === 'formula') {
              state = applyBoardAction(state, {
                eventId, action: 'formula',
                content: { latex: e.latex, display_mode: e.display_mode ? 'block' : 'inline' },
                highlighted: false, timestamp: e.seq ?? 0,
              });
            } else if (e.type === 'table') {
              state = applyBoardAction(state, {
                eventId, action: 'table',
                content: { title: e.title, columns: e.columns, rows: e.rows },
                highlighted: false, timestamp: e.seq ?? 0,
              });
            } else if (e.type === 'image') {
              state = applyBoardAction(state, {
                eventId, action: 'image',
                content: { src: e.src, caption: e.caption, media_type: e.media_type },
                highlighted: false, timestamp: e.seq ?? 0,
              });
            }
          }
          setBoardItems(state);
          setLoaded(true);
          setStatusText('板书回看');
          return;  // 静态终态，无需播放器/口型/自动播放
        }

        let player: Player | StreamingPlayer;
        if (PUSH_MODE) {
          // push 模式：空缓冲起播（先进 waiting），事件由父页面 postMessage 推入
          const sp = new StreamingPlayer([], TEACHER_ID, API_BASE, AUTH_TOKEN, { live: true });
          const onMessage = (ev: MessageEvent) => {
            if (ev.origin !== window.location.origin) return;
            const msg = ev.data;
            if (!msg || msg.source !== 'edunuwa' || msg.session !== PUSH_SESSION) return;
            if (msg.type === 'm6:init' || msg.type === 'm6:events') {
              if (Array.isArray(msg.events) && msg.events.length) sp.appendEvents(msg.events);
              if (msg.type === 'm6:init' && msg.done) sp.endOfStream();
            } else if (msg.type === 'm6:done') {
              sp.endOfStream();
            } else if (msg.type === 'm6:error') {
              if (msg.partial) sp.endOfStream(); // 已有部分事件：照常播完
              else setStatusText(`生成失败：${msg.message || '未知错误'}`);
            }
          };
          window.addEventListener('message', onMessage);
          removeMessageListener = () => window.removeEventListener('message', onMessage);
          player = sp;
        } else if (STREAM_MODE && EVENTS_URL) {
          // 流式模式：加载事件列表，逐句按需合成、顺序队列播放
          const resp = await fetch(EVENTS_URL, { headers: fetchHeaders });
          if (!resp.ok) throw new Error(`HTTP ${resp.status} - ${resp.statusText}`);
          const ed = await resp.json();
          player = new StreamingPlayer(ed.events || [], TEACHER_ID || ed.teacher_id || '', API_BASE, AUTH_TOKEN);
        } else {
          // 静态模式（兼容旧 playback_data）
          const resp = await fetch(PLAYBACK_URL, { headers: fetchHeaders });
          if (!resp.ok) throw new Error(`HTTP ${resp.status} - ${resp.statusText}`);
          const data: PlaybackData = await resp.json();
          const p = new Player();
          await p.load(data);
          player = p;
        }

        // 写新一条板书时计算它所属的聚焦组：上次写板书后讲过话 → 开新组并放大、旧组缩回。
        // 同时把活跃组设为该组。返回组号供写入 BoardStateItem.groupId。
        const nextBoardGroup = (): number => {
          if (speakSinceBoardRef.current) {
            groupCounterRef.current += 1;
            speakSinceBoardRef.current = false;
          }
          setActiveGroupId(groupCounterRef.current);
          return groupCounterRef.current;
        };

        // Wire events
        player.on('timeline:item', (evt) => {
          const item = evt.data as TimelineItem;
          if (item.type === 'board') {
            const boardItem: BoardStateItem = {
              eventId: item.event_id,
              action: item.action,
              content: item.content,
              highlighted: false,
              timestamp: Date.now(),
            };
            // 仅「写内容」类动作参与聚焦分组；highlight 只是切换高亮、clear_board 清屏，不开新组
            if (item.action === 'clear_board') {
              speakSinceBoardRef.current = false; // 清屏后下一段板书重新以放大形式聚焦
            } else if (item.action !== 'highlight') {
              boardItem.groupId = nextBoardGroup();
            }
            setBoardItems(prev => applyBoardAction(prev, boardItem));
          } else if (item.type === 'formula') {
            const fi = item as FormulaItem;
            const gid = nextBoardGroup();   // 先算组号（含 ref 自增/setActiveGroupId），勿放进 setState 更新函数
            setBoardItems(prev => [...prev, {
              eventId: fi.event_id,
              action: 'formula',
              content: { latex: fi.latex, display_mode: fi.display_mode },
              highlighted: false,
              timestamp: Date.now(),
              groupId: gid,
            }]);
          } else if (item.type === 'table') {
            const ti = item as TableItem;
            const gid = nextBoardGroup();
            setBoardItems(prev => [...prev, {
              eventId: ti.event_id,
              action: 'table',
              content: { title: ti.title, columns: ti.columns, rows: ti.rows },
              highlighted: false,
              timestamp: Date.now(),
              groupId: gid,
            }]);
          } else if (item.type === 'image') {
            const ii = item as ImageItem;
            const gid = nextBoardGroup();
            setBoardItems(prev => [...prev, {
              eventId: ii.event_id,
              action: 'image',
              content: { src: ii.src, caption: ii.caption, media_type: ii.media_type },
              highlighted: false,
              timestamp: Date.now(),
              groupId: gid,
            }]);
          } else if (item.type === 'speak') {
            // 讲解开始：标记「写板书后讲过话」——保持当前组放大，直到下一段新板书写出才缩回
            speakSinceBoardRef.current = true;
            setCurrentText(item.text);
          } else if (item.type === 'quiz') {
            setCurrentText(`[Quiz] ${item.question}`);
          }
        });

        player.on('audio:end', () => setCurrentText(''));
        player.on('end', () => {
          setCurrentText('');
          setStatusText('讲解结束');
          setIsPlaying(false);
          setEnded(true);
          if (PUSH_MODE) {
            window.parent.postMessage(
              { source: 'edunuwa', session: PUSH_SESSION, type: 'm5:end' },
              window.location.origin,
            );
          }
        });
        if (PUSH_MODE) {
          player.on('waiting', () => setStatusText('老师正在思考…'));
          player.on('resumed', () => setStatusText('讲解中…'));
        }

        // Setup LipSync
        const analyser = player.getAnalyserNode();
        if (analyser) {
          let lastSpeaking = false;
          const lipSync = new LipSync(analyser, (v: number) => {
            setMouthOpen(v);
            // hostAvatar 模式：只在「张/合」状态翻转时回传，避免每帧刷父页
            if (HOST_AVATAR) {
              const speaking = v > 0.15;
              if (speaking !== lastSpeaking) {
                lastSpeaking = speaking;
                window.parent.postMessage(
                  { source: 'edunuwa', session: PUSH_SESSION, type: 'm5:speaking', value: speaking },
                  window.location.origin,
                );
              }
            }
          });
          lipSync.start();
          lipSyncRef.current = lipSync;
        }

        playerRef.current = player;
        setLoaded(true);

        // 自动开始播放（父页 iframe 已带 allow="autoplay"）；push 模式先进
        // waiting，首个 speak 事件一到即开口
        player.play();
        setIsPlaying(true);
        setStatusText(PUSH_MODE ? '老师正在思考…' : '讲解中…');

        if (PUSH_MODE) {
          // 握手：通知父页面可以开始推事件（父页对重复 ready 会重发全量，
          // 因此 iframe 意外 reload 也能自愈）
          window.parent.postMessage(
            { source: 'edunuwa', session: PUSH_SESSION, type: 'm5:ready' },
            window.location.origin,
          );
        }
      } catch (e: any) {
        const msg = `加载失败：${e.message || String(e)}`;
        setStatusText(msg);
        setLoaded(false);
        console.error('[App] Load failed:', e);
        document.title = 'M5 Error';
        const el = document.getElementById('root');
        if (el) el.style.color = '#de5e39';
      }
    };

    init();

    return () => {
      removeMessageListener?.();
      lipSyncRef.current?.destroy();
      playerRef.current?.destroy();
    };
  }, []);

  const togglePlay = useCallback(() => {
    const p = playerRef.current;
    if (!p || ended) return;
    if (isPlaying) {
      p.pause();
      setIsPlaying(false);
      setStatusText('已暂停');
    } else {
      p.play();
      setIsPlaying(true);
      setStatusText('讲解中…');
    }
  }, [isPlaying, ended]);

  const handleSpeed = useCallback((rate: number) => {
    playerRef.current?.setSpeed(rate);
  }, []);

  return (
    <div className="app">
      {!loaded ? (
        <div className="app-loading"><p>{statusText}</p></div>
      ) : (
        <main className={`app-main${HOST_AVATAR ? ' app-main--solo' : ''}`}>
            <div className="board-frame">
              <div className="board-area">
                <div className="chalk-status"><span className="chalk-dot" />{statusText}</div>
                {/* 播放控制：黑板左下角，图标式（三角播放 / 双竖线暂停）。回看静态模式无播放器，隐藏 */}
                {!RENDER_ONLY && (
                <div className="board-controls">
                  <button className="board-ctl-btn" onClick={togglePlay} disabled={ended}
                    aria-label={isPlaying ? '暂停' : '播放'} title={isPlaying ? '暂停' : '播放'}>
                    {isPlaying ? (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4.2" height="14" rx="1" /><rect x="13.8" y="5" width="4.2" height="14" rx="1" /></svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>
                    )}
                  </button>
                  <select className="board-ctl-speed" onChange={e => handleSpeed(Number(e.target.value))} defaultValue="1.0" aria-label="倍速">
                    <option value="0.75">0.75×</option>
                    <option value="1.0">1.0×</option>
                    <option value="1.25">1.25×</option>
                    <option value="1.5">1.5×</option>
                  </select>
                </div>
                )}
                <Blackboard items={boardItems} currentText={currentText} activeGroupId={activeGroupId} />
              </div>
              <div className="chalk-tray"><span className="chalk-piece" /><span className="eraser" /></div>
            </div>
            {!HOST_AVATAR && (
              <div className="app-avatar">
                {AVATAR_URL ? (
                  <div style={{ textAlign: 'center' }}>
                    {AVATAR_URL_ALT ? (
                      <img src={mouthOpen > 0.15 ? AVATAR_URL_ALT : AVATAR_URL}
                        alt={TEACHER_NAME}
                        style={{
                          width: 140, height: 140, borderRadius: 16, objectFit: 'cover',
                          border: `3px solid ${mouthOpen > 0.15 ? '#de5e39' : '#4a3f33'}`,
                          transition: 'border-color 0.1s',
                        }} />
                    ) : (
                      <img src={AVATAR_URL} alt={TEACHER_NAME}
                        style={{ width: 140, height: 140, borderRadius: 16, objectFit: 'cover', border: '3px solid #de5e39' }} />
                    )}
                    <p style={{ color: '#d8cfc0', marginTop: 10, fontSize: 14, fontFamily: "'Songti SC','STSong',serif" }}>{TEACHER_NAME}</p>
                  </div>
                ) : (
                  <Live2DStage mouthOpen={mouthOpen} teacherName={TEACHER_NAME} />
                )}
              </div>
            )}
        </main>
      )}
    </div>
  );
}
