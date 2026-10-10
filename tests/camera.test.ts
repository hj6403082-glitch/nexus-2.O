import { test } from 'node:test';
import assert from 'node:assert/strict';
import { composeShot, IDLE_LOOK } from '../src/rendering/camera';
test('with no shot active the camera holds its idle framing', () => {
  const s = composeShot();
  assert.deepEqual([s.dx, s.dy, s.dz], [0, 0, 0]);
  assert.deepEqual([s.lx, s.ly, s.lz], IDLE_LOOK);
  // The boot state (LOCKED: every amount zero) must be perfectly stationary.
  assert.deepEqual(composeShot({ approach: 0, grouped: 0, project: 0, arc: 5 }), composeShot());
});
test('opening a module cranes down and tips the gaze toward the card', () => {
  const s = composeShot({ approach: 1 });
  assert.ok(s.dy < 0, 'camera lowers');
  assert.ok(s.ly < IDLE_LOOK[1], 'gaze lowers');
  assert.ok(s.lz < IDLE_LOOK[2], 'gaze pushes deeper toward the rising card');
  // The crane does not dolly on z — that is the presentation push, kept separate.
  assert.equal(s.dz, 0);
});
test('gathering pulls the camera back and up to frame the grid', () => {
  const s = composeShot({ grouped: 1 });
  assert.ok(s.dz > 0, 'pulls back');
  assert.ok(s.dy > 0, 'rises');
  // Half-gathered is proportionally half the move: the ease is linear in amount.
  const half = composeShot({ grouped: .5 });
  assert.ok(Math.abs(half.dz - s.dz / 2) < 1e-9 && Math.abs(half.dy - s.dy / 2) < 1e-9);
});
test('entering a project world dollies in and leads the gaze into it', () => {
  const s = composeShot({ project: 1, arc: 0 });
  assert.ok(s.dz < 0, 'dollies toward the island');
  assert.ok(s.lz < IDLE_LOOK[2], 'gaze leads into the world');
  assert.ok(s.dy > 0, 'floats up slightly');
  // The lateral arc is the only source of horizontal motion, and only with a world.
  assert.equal(composeShot({ project: 1, arc: 0 }).dx, 0);
  assert.ok(Math.abs(composeShot({ project: 1, arc: Math.PI / 2 }).dx) > 0);
  assert.equal(composeShot({ project: 0, arc: Math.PI / 2 }).dx, 0);
});
test('amounts are clamped so out-of-range inputs cannot fling the camera', () => {
  const over = composeShot({ grouped: 5, project: 5 });
  const one = composeShot({ grouped: 1, project: 1, arc: 0 });
  assert.deepEqual([over.dx, over.dy, over.dz], [one.dx, one.dy, one.dz]);
  const under = composeShot({ grouped: -3 });
  assert.deepEqual([under.dy, under.dz], [0, 0]);
});
