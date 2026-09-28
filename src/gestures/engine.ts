import type { Gesture } from '@/stores/nexus';
export type Point = { x: number; y: number; z: number };
export type GestureResult = { gesture: Gesture; event: Gesture | null; x: number; y: number; scale: number; pinching: boolean; frozen: boolean };
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export class GestureEngine {
  private pinch = false;
  private pinchScale = 0;
  private samples: { x: number; y: number; time: number }[] = [];
  private cooldown = 0;
  private heldSince = 0;
  private stillPoint: Point | null = null;
  reset() { this.pinch = false; this.pinchScale = 0; this.samples = []; this.heldSince = 0; this.stillPoint = null; this.cooldown = 0; }
  update(points: Point[], now: number): GestureResult | null {
    if (points.length < 21) { this.reset(); return null; }
    const wrist = points[0], palm = points[9];
    const scale = distance(wrist, palm);
    if (scale < .025) { this.reset(); return null; }
    const x = 1 - (points[0].x + points[5].x + points[17].x) / 3;
    const y = (points[0].y + points[5].y + points[17].y) / 3;
    const ratio = distance(points[4], points[8]) / scale;
    const pinching = ratio < (this.pinch ? .48 : .32); // Hysteresis avoids repeated grab/drop.
    const fingers = [8, 12, 16, 20].filter(tip => distance(points[tip], wrist) > distance(points[tip - 2], wrist) * 1.2).length;
    let gesture: Gesture = pinching ? 'Pinch' : fingers >= 3 ? 'Open palm' : fingers === 0 ? 'Closed hand' : 'None';
    let event: Gesture | null = null;
    if (pinching && !this.pinch) { event = 'Pinch'; this.pinchScale = scale; this.samples = []; }
    if (!pinching && this.pinch) { event = 'Release'; gesture = 'Release'; this.pinchScale = 0; }
    if (pinching && this.pinchScale && now > this.cooldown) {
      if (scale / this.pinchScale > 1.35) { event = 'Pull'; this.cooldown = now + 1000; this.pinchScale = scale; }
      else if (scale / this.pinchScale < .72) { event = 'Push'; this.cooldown = now + 1000; this.pinchScale = scale; }
    }
    this.samples.push({ x, y, time: now });
    this.samples = this.samples.filter(s => now - s.time < 650);
    if (!pinching && fingers >= 3 && now > this.cooldown && this.samples.length > 4) {
      const first = this.samples[0], dx = x - first.x, dy = y - first.y;
      if (Math.abs(dx) > .19 && Math.abs(dy) < .12 && now - first.time < 600) {
        event = dx < 0 ? 'Swipe left' : 'Swipe right'; gesture = event;
        this.cooldown = now + 750; this.samples = [];
      }
    }
    // Circle is reserved for the AI wake system. Require a closed, substantial path.
    if (!pinching && fingers < 3 && this.samples.length >= 12 && now > this.cooldown) {
      const samples = this.samples;
      const minX = Math.min(...samples.map(p => p.x)), maxX = Math.max(...samples.map(p => p.x));
      const minY = Math.min(...samples.map(p => p.y)), maxY = Math.max(...samples.map(p => p.y));
      const a = samples[0];
      const length = samples.slice(1).reduce((sum, p, i) => sum + Math.hypot(p.x - samples[i].x, p.y - samples[i].y), 0);
      if (maxX - minX > .13 && maxY - minY > .13 && Math.hypot(x - a.x, y - a.y) < .065 && length > .5) {
        event = 'Circle'; gesture = event; this.cooldown = now + 1600; this.samples = [];
      }
    }
    if (fingers >= 3 && !pinching && !event) {
      if (!this.stillPoint || distance({ x, y, z: 0 }, this.stillPoint) > .035) { this.stillPoint = { x, y, z: 0 }; this.heldSince = now; }
    } else { this.stillPoint = null; this.heldSince = 0; }
    const frozen = this.heldSince > 0 && now - this.heldSince > 900;
    if (frozen) gesture = 'Hold';
    this.pinch = pinching;
    return { gesture, event, x, y, scale, pinching, frozen };
  }
}
