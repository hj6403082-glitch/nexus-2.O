type Point = { x: number; y: number; z?: number };
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export class BimanualGroup {
  private baseline = 0;
  private fired = false;
  update(hands: Point[][]): 'group' | 'split' | 'holding' | null {
    if (hands.length < 2 || hands.slice(0, 2).some(h => h.length < 21 || distance(h[4], h[8]) >= distance(h[0], h[9]) * .4)) { this.reset(); return null; }
    const span = distance(hands[0][9], hands[1][9]);
    if (span < .08) { this.reset(); return null; }
    if (!this.baseline) this.baseline = span;
    if (!this.fired && span / this.baseline < .7) { this.fired = true; return 'group'; }
    if (!this.fired && span / this.baseline > 1.4) { this.fired = true; return 'split'; }
    return 'holding';
  }
  reset() { this.baseline = 0; this.fired = false; }
}
export class BimanualZoom {
  private baseline = 0;
  private initial = 1;
  update(hands: Point[][], current: number): number | null {
    if (hands.length < 2 || hands.some(h => h.length < 21)) { this.reset(); return null; }
    const pinching = hands.slice(0, 2).every(h => distance(h[4], h[8]) < distance(h[0], h[9]) * .4);
    const span = distance(hands[0][9], hands[1][9]);
    if (!pinching || span < .08) { this.reset(); return null; }
    if (!this.baseline) { this.baseline = span; this.initial = current; }
    return Math.max(.75, Math.min(1.35, this.initial * span / this.baseline));
  }
  reset() { this.baseline = 0; }
}
