import { test } from 'node:test';
import assert from 'node:assert/strict';
import { envelopes, FormTimeline } from '../src/embodiment/timeline';
test('a throttled preview does not stretch an eight-second transition into minutes', () => { const clock = new FormTimeline(); clock.target = 'human'; for (let i = 0; i < 8; i++) clock.step(1, true); assert.equal(clock.phase, 'HUMANOID_ACTIVE'); });
test('form waits for the frozen particle buffer before dissolving', () => {
  const clock = new FormTimeline(); clock.target = 'human';
  for (let i = 0; i < 600; i++) clock.step(1 / 60, false);
  assert.equal(clock.time, .45); assert.equal(envelopes(clock.time).dissolve, 0);
});
test('forward and reverse use the same clock and settle exactly', () => {
  const clock = new FormTimeline(); clock.target = 'human';
  for (let i = 0; i < 600; i++) clock.step(1 / 60, true);
  assert.equal(clock.phase, 'HUMANOID_ACTIVE'); assert.equal(clock.time, 8);
  clock.target = 'spatial'; clock.step(1 / 60, true);
  assert.equal(clock.phase, 'RETURNING'); assert.ok(Math.abs(clock.time - (8 - 1.7 / 60)) < 1e-10);
  for (let i = 0; i < 600; i++) clock.step(1 / 60, true);
  assert.equal(clock.time, 0); assert.equal(clock.phase, 'NORMAL');
});
test('form envelopes stay finite and bounded through the journey', () => {
  for (let t = 0; t <= 8; t += .01) for (const v of Object.values(envelopes(t))) assert.ok(Number.isFinite(v) && v >= 0 && v <= 1);
});
test('surface sampling returns exactly the requested count with no near-duplicates', async () => {
  const { poissonSelect } = await import('../src/embodiment/bake');
  const c = new Float32Array(20000 * 3); let seed = 3; const r = () => (seed = seed * 16807 % 2147483647) / 2147483647;
  for (let i = 0; i < 20000; i++) c.set([r() - .5, r() - .5, r() * .2], i * 3);
  const picked = await poissonSelect(c, 3000);
  assert.equal(picked.length, 3000); assert.equal(new Set(picked).size, 3000);
});
test('transition FX envelopes peak during ignition and the materialisation scan', () => {
  assert.ok(envelopes(3.4).ignite > .9); assert.equal(envelopes(1).ignite, 0); assert.equal(envelopes(8).ignite, 0);
  assert.equal(envelopes(3).scan, 0); assert.equal(envelopes(8).scan, 1);
});
