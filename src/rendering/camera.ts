// Phase 4 — cinematic camera choreography. The orbit camera has a few named
// "shots" that compose into a single offset from its idle framing: a crane-down
// as a module opens, a pull-back that frames the grid when cards gather, and a
// slow dolly-and-arc toward a project's floating world. Each shot is driven by a
// smooth 0..1 amount (envelopes and springs computed by the scene), so the moves
// ease in and out and never fight each other. Pure and deterministic, so the
// composition is unit-tested rather than eyeballed.
export type CameraShot = { dx: number; dy: number; dz: number; lx: number; ly: number; lz: number };
// The idle gaze the orbit looks at when every amount is zero.
export const IDLE_LOOK: [number, number, number] = [0, .2, -2];
const clamp01 = (n: number) => (n < 0 ? 0 : n > 1 ? 1 : n);
export function composeShot(input: { approach?: number; grouped?: number; project?: number; arc?: number } = {}): CameraShot {
  const approach = clamp01(input.approach ?? 0);
  const grouped = clamp01(input.grouped ?? 0);
  const project = clamp01(input.project ?? 0);
  const arc = input.arc ?? 0;
  let [lx, ly, lz] = IDLE_LOOK;
  let dx = 0, dy = 0, dz = 0;
  // Opening a module: a gentle crane down and a tip of the gaze toward the card
  // that rises to meet the camera. (The dolly-in itself is the presentation push,
  // kept separate, so this only adds the vertical nuance.)
  dy -= approach * .22;
  ly -= approach * .18;
  lz -= approach * .35;
  // Gathering: lift and pull back to frame the whole cluster grid, gaze settling
  // onto the nearer grid plane.
  dy += grouped * .9;
  dz += grouped * 1.5;
  ly -= grouped * .12;
  lz += grouped * .5;
  // Entering a project world: dolly toward the floating island at ~[0,.35,-5.2]
  // with a slow lateral arc for parallax, the gaze leading into the world.
  dz -= project * 2.6;
  dy += project * .18;
  dx += Math.sin(arc) * project * .5;
  ly += project * .15;
  lz -= project * 3.2;
  lx += Math.sin(arc) * project * .2;
  return { dx, dy, dz, lx, ly, lz };
}
