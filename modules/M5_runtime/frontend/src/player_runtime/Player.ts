// PlayerRuntime implementation per M5_runtime.md §3.2 and §9.2
import { AudioPlayer } from './AudioPlayer';
import { EventScheduler } from './EventScheduler';
import { QuizHandler } from './QuizHandler';
import { resolveAudioPath } from '../shared/audioPathResolver';
import type {
  PlaybackData, TimelineItem, QuizItem,
  PlayerRuntime, PlayerEventName, PlayerEventHandler, PlayerEvent,
} from './types';
import { VALID_EVENT_TYPES, VALID_SPEEDS } from './types';

type PlayerState = 'idle' | 'loading' | 'ready' | 'playing' | 'paused' | 'destroyed';

export class Player implements PlayerRuntime {
  private _state: PlayerState = 'idle';
  private _playback: PlaybackData | null = null;
  private _audioPlayer = new AudioPlayer();
  private _scheduler = new EventScheduler();
  private _quizHandler = new QuizHandler();
  private _listeners = new Map<PlayerEventName, Set<PlayerEventHandler>>();

  async load(playback: PlaybackData): Promise<void> {
    this._state = 'loading';

    // H1: validate all timeline item types
    for (const item of playback.timeline) {
      if (!VALID_EVENT_TYPES.has(item.type)) {
        throw new Error(`Unknown timeline event type: "${(item as any).type}" at seq ${item.seq}`);
      }
    }

    // Resolve audio paths and preload
    const speakItems = playback.timeline.filter((t): t is TimelineItem & { type: 'speak' } => t.type === 'speak');
    const preloads = speakItems.map((item) => {
      const url = resolveAudioPath(item.audio_path);
      return this._audioPlayer.preload(item.event_id, url);
    });
    await Promise.all(preloads);

    this._playback = playback;
    this._state = 'ready';
  }

  play(): void {
    if (this._state === 'destroyed' || !this._playback) return;
    if (this._state === 'playing') return;

    // Resume AudioContext on user gesture
    const analyser = this._audioPlayer.getAnalyserNode();
    const ctx = analyser.context as AudioContext;
    if (ctx.state === 'suspended') {
      ctx.resume();
    }

    if (this._state === 'paused') {
      this._scheduler.resume();
      this._audioPlayer.resume();
    } else {
      this._startPlayback();
    }

    this._state = 'playing';
    this._emit('play', {});
  }

  pause(): void {
    if (this._state !== 'playing') return;
    this._scheduler.pause();
    this._audioPlayer.pause();
    this._state = 'paused';
    this._emit('pause', {});
  }

  seek(seq: number): void {
    if (!this._playback) return;
    const item = this._playback.timeline.find(t => t.seq === seq);
    if (!item) return;

    this._scheduler.stop();
    this._audioPlayer.stop();

    // Rebuild board state up to the seek target
    const priorItems = this._playback.timeline.filter(t => t.seq <= seq);
    for (const prior of priorItems) {
      this._emit('timeline:item', prior);
    }

    this._scheduler.start(
      this._playback.timeline,
      (i) => this._handleTimelineItem(i),
      () => this._handleSessionEnd(),
    );
    this._scheduler.seekTo(item.start_offset_sec);

    if (this._state === 'playing') {
      this._scheduler.resume();
      this._audioPlayer.resume();
    } else {
      this._scheduler.pause();
    }

    this._emit('seek', { seq });
  }

  setSpeed(rate: number): void {
    if (!VALID_SPEEDS.has(rate)) {
      console.warn(`[Player] Invalid speed ${rate}, ignoring`);
      return;
    }
    this._audioPlayer.setPlaybackRate(rate);
    this._scheduler.setSpeed(rate);
    this._emit('speedchange', { rate });
  }

  on(event: PlayerEventName, cb: PlayerEventHandler): void {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    this._listeners.get(event)!.add(cb);
  }

  destroy(): void {
    this._scheduler.stop();
    this._quizHandler.destroy();
    this._audioPlayer.destroy();
    this._listeners.clear();
    this._playback = null;
    this._state = 'destroyed';
  }

  // Expose analyser for LipSync
  getAnalyserNode(): AnalyserNode {
    return this._audioPlayer.getAnalyserNode();
  }

  // --- Private ---

  private _startPlayback(): void {
    if (!this._playback) return;

    this._scheduler.start(
      this._playback.timeline,
      (item) => this._handleTimelineItem(item),
      () => this._handleSessionEnd(),
    );
  }

  private _handleTimelineItem(item: TimelineItem): void {
    this._emit('timeline:item', item);

    if (item.type === 'speak') {
      this._emit('audio:start', { event_id: item.event_id, text: item.text });
      this._audioPlayer.play(item.event_id);

      // After duration, emit audio:end
      const timeout = item.duration_sec * 1000;
      setTimeout(() => {
        this._emit('audio:end', { event_id: item.event_id });
      }, Math.max(timeout, 100));
    }

    if (item.type === 'quiz' && (item as QuizItem).blocking) {
      this._audioPlayer.pause();
      this._quizHandler.show(item.question, item.options).then((answer) => {
        this._emit('timeline:item', { ...item, answer } as any);
        this._scheduler.resolveQuiz(answer);
        this._audioPlayer.resume();
      });
    }
  }

  private _handleSessionEnd(): void {
    this._state = 'ready';
    this._emit('end', {});
  }

  private _emit(type: PlayerEventName, data?: any): void {
    const handlers = this._listeners.get(type);
    if (!handlers) return;
    const event: PlayerEvent = { type, data };
    handlers.forEach(cb => cb(event));
  }
}
