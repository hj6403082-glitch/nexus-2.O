import type { WorldGrade } from '@/stores/world';
// Phase 3 — every project is a place you can return to. A project's identity
// (its id and title) is hashed into a deterministic "floating world": a filmic
// grade, an accent, and the geometry of the little island that materializes
// ahead of you when you enter it. Same project always yields the same world,
// so re-entering feels like walking back into a room you know.
export type ProjectWorld = {
  seed: number;
  accent: string;          // hex, kept in NEXUS's cool band so gold stays "earned"
  grade: WorldGrade;       // same shape as the six base worlds
  rings: number;           // 2–4 slowly counter-rotating halo rings
  shards: number;          // 5–11 light shards orbiting the platform
  tilt: number;            // ring tilt, radians
  spin: number;            // ring spin rate (signed)
  bob: number;             // vertical bob speed
  phase: number;           // bob phase offset, so two worlds never breathe in sync
};
// FNV-1a over the id+title: stable across runs, well spread for short strings.
export function hashSeed(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}
// A small deterministic stream of [0,1) values from one seed.
function stream(seed: number) {
  let s = seed || 1;
  return () => { s = Math.imul(s ^ (s >>> 15), 0x2c1b3c6d); s = Math.imul(s ^ (s >>> 12), 0x297a2d39); s ^= s >>> 15; return (s >>> 0) / 4294967296; };
}
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
// HSL→hex, S/L fixed so every project world stays legible and on-brand.
function coolHex(hue: number, sat: number, light: number): string {
  const c = (1 - Math.abs(2 * light - 1)) * sat, x = c * (1 - Math.abs(((hue / 60) % 2) - 1)), m = light - c / 2;
  const [r, g, b] = hue < 60 ? [c, x, 0] : hue < 120 ? [x, c, 0] : hue < 180 ? [0, c, x] : hue < 240 ? [0, x, c] : hue < 300 ? [x, 0, c] : [c, 0, x];
  const to = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, '0');
  return `#${to(r)}${to(g)}${to(b)}`;
}
export function projectWorld(project: { id: string; title: string }): ProjectWorld {
  const seed = hashSeed(`${project.id}::${project.title}`);
  const rnd = stream(seed);
  // Hue stays inside the cyan→indigo band (185°–255°): distinct per project,
  // never straying into the reserved gold/warning warmths.
  const hue = lerp(185, 255, rnd());
  const accent = coolHex(hue, lerp(.45, .7, rnd()), lerp(.55, .68, rnd()));
  // A grade within the same tasteful bounds the six base worlds use.
  const warmth = lerp(-.18, .08, rnd());
  const grade: WorldGrade = {
    contrast: Number(lerp(.95, 1.18, rnd()).toFixed(3)),
    warmth: Number(warmth.toFixed(3)),
    shadow: [Number((rnd() * .02).toFixed(3)), Number((rnd() * .012).toFixed(3)), Number(lerp(.03, .07, rnd()).toFixed(3))],
    highlight: [Number((rnd() * .02).toFixed(3)), Number((rnd() * .025).toFixed(3)), Number(lerp(.01, .04, rnd()).toFixed(3))],
    halation: Number(lerp(.1, .22, rnd()).toFixed(3)),
  };
  return {
    seed, accent, grade,
    rings: 2 + Math.floor(rnd() * 3),
    shards: 5 + Math.floor(rnd() * 7),
    tilt: lerp(-.5, .5, rnd()),
    spin: (rnd() < .5 ? -1 : 1) * lerp(.05, .18, rnd()),
    bob: lerp(.3, .6, rnd()),
    phase: rnd() * Math.PI * 2,
  };
}
