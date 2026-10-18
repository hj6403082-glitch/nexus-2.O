// One-euro filter (Casiez et al.): adaptive low-pass smoothing for pointer
// signals. Slow movement is heavily smoothed to remove jitter; fast movement is
// barely smoothed, so the cursor keeps up with the hand without lag.
export class OneEuro {
  private x: number | null = null; private dx = 0; private time = 0;
  constructor(private minCutoff = 1.4, private beta = 9, private dCutoff = 1) {}
  private static alpha(cutoff: number, dt: number) { const tau = 1 / (2 * Math.PI * cutoff); return 1 / (1 + tau / dt); }
  reset() { this.x = null; this.dx = 0; this.time = 0; }
  filter(value: number, now: number) {
    if (this.x === null) { this.x = value; this.time = now; return value; }
    const dt = Math.max(.001, (now - this.time) / 1000); this.time = now;
    const rawDx = (value - this.x) / dt;
    this.dx += OneEuro.alpha(this.dCutoff, dt) * (rawDx - this.dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x += OneEuro.alpha(cutoff, dt) * (value - this.x);
    return this.x;
  }
}
