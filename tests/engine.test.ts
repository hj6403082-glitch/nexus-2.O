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
