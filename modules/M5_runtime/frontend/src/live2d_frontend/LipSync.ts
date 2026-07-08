// LipSync: Web Audio API AnalyserNode → RMS → smoothed mouth value
// Per M5_runtime.md §9.4: RMS-driven, not phoneme-level
export class LipSync {
  private _analyser: AnalyserNode;
  private _dataArray: Uint8Array;
  private _rafId: number | null = null;
  private _onUpdate: (value: number) => void;
  private _smoothing: number;
  private _lastValue: number;

  constructor(analyser: AnalyserNode, onUpdate: (value: number) => void) {
    this._analyser = analyser;
    this._dataArray = new Uint8Array(analyser.fftSize);
    this._onUpdate = onUpdate;
    this._smoothing = 0.7;
    this._lastValue = 0;
  }

  start(): void {
    if (this._rafId !== null) return;
    const tick = () => {
      this._analyser.getByteTimeDomainData(this._dataArray as any);
      let sum = 0;
      for (let i = 0; i < this._dataArray.length; i++) {
        const v = (this._dataArray[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / this._dataArray.length);
      const normalized = Math.min(rms / 0.2, 1.0);
      this._lastValue = this._lastValue * this._smoothing + normalized * (1 - this._smoothing);
      this._onUpdate(this._lastValue);
      this._rafId = requestAnimationFrame(tick);
    };
    tick();
  }

  stop(): void {
    if (this._rafId !== null) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
  }

  destroy(): void {
    this.stop();
  }
}
