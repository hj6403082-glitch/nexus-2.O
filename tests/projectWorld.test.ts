import { test } from 'node:test';
import assert from 'node:assert/strict';
import { projectWorld, hashSeed } from '../src/knowledge/projectWorld';
const sample = (id: string, title: string) => projectWorld({ id, title });
// sRGB HSL straight from the hex — three's Color applies colour management and
// would report linearised values, which is not what the accent means on screen.
function hsl(hex: string) {
  const n = parseInt(hex.slice(1), 16), r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  let h = 0;
  if (d) { h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4; h *= 60; if (h < 0) h += 360; }
  return { h, s: d ? d / (1 - Math.abs(2 * l - 1)) : 0, l };
}
test('a project world is deterministic: same identity yields the same world', () => {
  const a = sample('p1', 'Aurora'), b = sample('p1', 'Aurora');
  assert.deepEqual(a, b);
  assert.equal(hashSeed('p1::Aurora'), hashSeed('p1::Aurora'));
});
test('different projects get different worlds', () => {
  const a = sample('p1', 'Aurora'), b = sample('p2', 'Borealis'), c = sample('p1', 'Renamed');
  assert.notEqual(a.seed, b.seed);
  // The title is part of the identity, so renaming re-skins the world.
  assert.notEqual(a.seed, c.seed);
  assert.notEqual(a.accent, b.accent);
});
test('the accent stays in the cool band, never straying into the reserved golds', () => {
  for (let i = 0; i < 200; i++) {
    const { accent } = sample(`id-${i}`, `Project ${i * 7}`);
    assert.match(accent, /^#[0-9a-f]{6}$/i);
    const { h, l } = hsl(accent);
    // Cyan→indigo only: well clear of gold (~45°) and warning orange (~27°).
    assert.ok(h >= 180 && h <= 260, `accent hue ${h.toFixed(0)}° out of the cool band`);
    assert.ok(l > .5 && l < .72, `accent lightness ${l.toFixed(2)} stays legible`);
  }
});
test('the derived grade shares the shape and bounds of the six base worlds', () => {
  for (let i = 0; i < 100; i++) {
    const { grade, rings, shards } = sample(`g-${i}`, `Grade ${i}`);
    assert.equal(grade.shadow.length, 3);
    assert.equal(grade.highlight.length, 3);
    assert.ok(grade.contrast >= .95 && grade.contrast <= 1.18);
    assert.ok(grade.warmth >= -.18 && grade.warmth <= .08);
    assert.ok(grade.halation >= .1 && grade.halation <= .22);
    // Geometry counts land in a renderable, tasteful range.
    assert.ok(rings >= 2 && rings <= 4);
    assert.ok(shards >= 5 && shards <= 11);
  }
});
