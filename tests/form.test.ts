import { test } from 'node:test';
import assert from 'node:assert/strict';
import { envelopes, FormTimeline } from '../src/embodiment/timeline';
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
