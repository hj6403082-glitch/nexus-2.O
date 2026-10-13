// Velocity flick & background orbit (Phase 8, Objective 2). A fast drag release
// with high velocity flings a card out to a dimmed outer orbit ring; a gentle
// release returns it to its slot. Pure helpers so the thresholds are testable.

export type Vec3 = [number, number, number];

// The release speed (in normalised screen units / second) above which a drag
// release counts as a flick rather than a drop-back.
export const FLICK_SPEED = 1.6;

// Decide whether a release is a flick. `vx`,`vy` are the hand-signal velocity at
// release (screen units per second). Returns the flick speed if it qualifies,
// else null.
export function detectFlick(vx: number, vy: number): number | null {
  const speed = Math.hypot(vx, vy);
  return speed >= FLICK_SPEED ? speed : null;
}

// Where a flung card sits in the outer, dimmed orbit ring. `angle` is the card's
// current orbit angle; the outer ring is wider and lifted, so flung cards form a
// halo behind the active orbit.
export function flungSlot(ordinal: number, angle: number): Vec3 {
  const radius = 8.4;
  return [Math.sin(angle) * radius, 1.1 + Math.sin(ordinal * 1.7) * .4, Math.cos(angle) * radius - 3.5];
}
