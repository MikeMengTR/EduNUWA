// Single-clock event scheduler per M5_runtime.md §9.1
// Uses requestAnimationFrame + performance.now() (NOT setTimeout) to avoid drift (H7)
import type { TimelineItem, QuizItem } from './types';

export class EventScheduler {
  private _timeline: TimelineItem[] = [];
  private _startTime = 0;
  private _accumulatedPause = 0;
  private _pauseStart = 0;
  private _rafId: number | null = null;
  private _speed = 1.0;
  private _isRunning = false;
  private _isPaused = false;
  private _firedSeqs = new Set<number>();
  private _onEvent: ((item: TimelineItem) => void) | null = null;
  private _onEnd: (() => void) | null = null;
  private _quizResolver: ((answer: string) => void) | null = null;
  private _isBlocked = false;

  get isRunning(): boolean { return this._isRunning; }
  get isPaused(): boolean { return this._isPaused; }

  start(timeline: TimelineItem[], onEvent: (item: TimelineItem) => void, onEnd: () => void): void {
    this.stop();
    this._timeline = [...timeline].sort((a, b) => a.start_offset_sec - b.start_offset_sec);
    this._onEvent = onEvent;
    this._onEnd = onEnd;
    this._firedSeqs.clear();
    this._accumulatedPause = 0;
    this._isBlocked = false;
    this._isRunning = true;
    this._isPaused = false;
    this._startTime = performance.now() / 1000;
    this._tick();
  }

  pause(): void {
    if (!this._isRunning || this._isPaused) return;
    this._isPaused = true;
    this._pauseStart = performance.now() / 1000;
  }

  resume(): void {
    if (!this._isRunning || !this._isPaused) return;
    this._accumulatedPause += performance.now() / 1000 - this._pauseStart;
    this._isPaused = false;
    if (!this._rafId) this._tick();
  }

  stop(): void {
    this._isRunning = false;
    this._isPaused = false;
    this._isBlocked = false;
    this._quizResolver = null;
    if (this._rafId !== null) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
  }

  setSpeed(rate: number): void {
    this._speed = rate;
  }

  seekTo(offsetSec: number): void {
    this._firedSeqs.clear();
    this._accumulatedPause = 0;
    this._isBlocked = false;
    this._quizResolver = null;
    // Pre-fire items before the seek target
    for (const item of this._timeline) {
      if (item.start_offset_sec < offsetSec) {
        this._firedSeqs.add(item.seq);
      }
    }
    this._startTime = performance.now() / 1000 - offsetSec / this._speed;
  }

  resolveQuiz(answer: string): void {
    if (this._quizResolver) {
      const resolve = this._quizResolver;
      this._quizResolver = null;
      this._isBlocked = false;
      // Account for quiz pause time
      this._accumulatedPause += performance.now() / 1000 - this._pauseStart;
      this._pauseStart = 0;
      resolve(answer);
      this._tick();
    }
  }

  getElapsed(): number {
    if (!this._isRunning) return 0;
    const now = performance.now() / 1000;
    const pauseTotal = this._isPaused
      ? this._accumulatedPause + (now - this._pauseStart)
      : this._accumulatedPause;
    return (now - this._startTime - pauseTotal) * this._speed;
  }

  private _tick(): void {
    if (!this._isRunning || this._isBlocked) return;

    this._rafId = requestAnimationFrame(() => this._tick());
    const elapsed = this.getElapsed();

    for (const item of this._timeline) {
      if (this._firedSeqs.has(item.seq)) continue;
      if (item.start_offset_sec <= elapsed) {
        this._firedSeqs.add(item.seq);
        this._onEvent?.(item);

        if (item.type === 'quiz' && (item as QuizItem).blocking) {
          this._isBlocked = true;
          this._pauseStart = performance.now() / 1000;
          // The caller must call resolveQuiz() to unblock
          return;
        }
      }
    }

    // Check session end
    if (this._firedSeqs.size >= this._timeline.length) {
      const last = this._timeline[this._timeline.length - 1];
      let lastEnd = last.start_offset_sec;
      if (last.type === 'speak') lastEnd += last.duration_sec;
      else if ('dwell_sec' in last && last.dwell_sec) lastEnd += last.dwell_sec;
      else if (last.type === 'pause') lastEnd += last.duration_sec;
      else lastEnd += 1.5; // default dwell for board/formula/table

      if (elapsed >= lastEnd) {
        this.stop();
        this._onEnd?.();
      }
    }
  }

  // Expose for quiz handling
  setQuizResolver(resolver: (answer: string) => void): void {
    this._quizResolver = resolver;
  }
}
