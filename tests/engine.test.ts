import { test } from 'node:test';
import assert from 'node:assert/strict';
import { GestureEngine, type Point } from '../src/gestures/engine';
import { stepSpring } from '../src/animations/spring';
function hand(offset = 0, pinch = false, size = 1): Point[] {
  const p = Array.from({ length: 21 }, () => ({ x: .5 + offset, y: .55, z: 0 }));
  p[0] = { x: .5 + offset, y: .75, z: 0 };
  p[9] = { x: .5 + offset, y: .55, z: 0 };
  for (const tip of [8, 12, 16, 20]) { p[tip] = { x: .5 + offset + (tip - 12) * .012, y: .23, z: 0 }; p[tip - 2] = { x: p[tip].x, y: .49, z: 0 }; }
  p[4] = { x: pinch ? p[8].x + .02 : .28 + offset, y: pinch ? p[8].y : .48, z: 0 };
  return p.map(point => ({ ...point, x: .5 + offset + (point.x - .5 - offset) * size, y: .75 + (point.y - .75) * size }));
}
test('pinch is edge-triggered and release fires once', () => {
  const engine = new GestureEngine();
  assert.equal(engine.update(hand(), 100)?.event, null);
  assert.equal(engine.update(hand(0, true), 200)?.event, 'Pinch');
  assert.equal(engine.update(hand(0, true), 300)?.event, null);
  assert.equal(engine.update(hand(), 400)?.event, 'Release');
  assert.equal(engine.update(hand(), 500)?.event, null);
});
test('pull and push use relative palm scale and respect cooldown', () => {
  const e = new GestureEngine(); e.update(hand(0, true), 100);
  assert.equal(e.update(hand(0, true, 1.5), 200)?.event, 'Pull');
  assert.equal(e.update(hand(0, true, 1), 300)?.event, null);
  assert.equal(e.update(hand(0, true, 1), 1300)?.event, 'Push');
});
test('open palm swipes are debounced and mirrored', () => {
  const e = new GestureEngine(); let events = [];
  for (let i = 0; i < 12; i++) { const r = e.update(hand(i * .04), 100 + i * 45); if (r?.event) events.push(r.event); }
  assert.deepEqual(events, ['Swipe left']);
});
test('still palm freezes and loss clears history', () => {
  const e = new GestureEngine(); e.update(hand(), 100);
  assert.equal(e.update(hand(), 1100)?.frozen, true);
  assert.equal(e.update([], 1200), null);
  assert.equal(e.update(hand(), 1300)?.frozen, false);
});
test('spring settles exactly and has zero zero-input drift', () => {
  const spring = { value: 2, velocity: 0 };
  for (let i = 0; i < 1200; i++) stepSpring(spring, 0, 1 / 60);
  assert.deepEqual(spring, { value: 0, velocity: 0 });
  for (let i = 0; i < 600; i++) stepSpring(spring, 0, 1 / 60);
  assert.deepEqual(spring, { value: 0, velocity: 0 });
});
function pose(up: number[], thumbUp = false): Point[] {
  const p = hand();
  // Curl every finger not listed: tip folds back below its middle joint.
  for (const tip of [8, 12, 16, 20]) if (!up.includes(tip)) p[tip] = { x: p[tip].x, y: .62, z: 0 };
  if (thumbUp) { p[4] = { x: .47, y: .2, z: 0 }; p[5] = { x: .48, y: .52, z: 0 }; }
  return p;
}
test('peace and thumbs up fire once after being held', () => {
  const e = new GestureEngine(); const events = [];
  for (let t = 0; t <= 1600; t += 100) events.push(e.update(pose([8, 12]), t)?.event);
  assert.deepEqual(events.filter(Boolean), ['Peace']);
  assert.equal(e.update(pose([8, 12]), 1700)?.gesture, 'Peace');
  const t2 = new GestureEngine(); const fired = [];
  for (let t = 0; t <= 1600; t += 100) fired.push(t2.update(pose([], true), t)?.event);
  assert.deepEqual(fired.filter(Boolean), ['Thumbs up']);
  assert.equal(new GestureEngine().update(pose([8]), 0)?.gesture, 'Point');
});
test('an open hand moved vertically swipes up or down', () => {
  const e = new GestureEngine(); let last = null;
  for (let i = 0; i < 6; i++) last = e.update(hand().map(p => ({ ...p, y: p.y - i * .04 })), 100 + i * 60)?.event ?? last;
  assert.equal(last, 'Swipe up');
});
test('one-euro smoothing steadies jitter but follows fast moves', async () => {
  const { OneEuro } = await import('../src/gestures/oneEuro');
  const f = new OneEuro(); let out = 0;
  for (let i = 0; i < 30; i++) out = f.filter(.5 + (i % 2 ? .004 : -.004), i * 16);
  assert.ok(Math.abs(out - .5) < .003);
  for (let i = 30; i < 40; i++) out = f.filter(.9, i * 16);
  assert.ok(out > .85);
});
