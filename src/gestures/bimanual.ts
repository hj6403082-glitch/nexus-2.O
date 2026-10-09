type Point = { x: number; y: number; z?: number };
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
// Two pinched hands set the orbit scale by how far apart they are.
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
// Two OPEN hands moving together gather the cards into a cluster; moving apart
// splits them back to the orbit. Open-handed, so it never collides with the
// pinch-based zoom. Edge-triggered: one event per decisive motion.
export type GroupEvent = 'group' | 'split';
export class BimanualGroup {
  private baseline = 0;
  private fired = false;
  update(hands: Point[][]): GroupEvent | null {
    if (hands.length < 2 || hands.some(h => h.length < 21)) { this.reset(); return null; }
    // Both hands open (fingertips well clear of the palm, thumb not pinched).
    const open = hands.slice(0, 2).every(h => {
      const palm = distance(h[0], h[9]);
      return palm > .02 && [8, 12, 16, 20].every(tip => distance(h[tip], h[0]) > palm * 1.1) && distance(h[4], h[8]) > palm * .5;
    });
    if (!open) { this.reset(); return null; }
    const span = distance(hands[0][9], hands[1][9]);
    // First open frame anchors the gesture: closing to the anchor groups,
    // opening from it splits. One event per gesture; re-arm when hands drop.
    if (!this.baseline) { this.baseline = span; return null; }
    if (this.fired) return null;
    if (span < this.baseline * .55) { this.fired = true; return 'group'; }
    if (span > this.baseline * 1.8) { this.fired = true; return 'split'; }
    return null;
  }
  reset() { this.baseline = 0; this.fired = false; }
}
