import test from 'node:test';
import assert from 'node:assert/strict';
import { fingerForPoint, fingers } from '../src/embodiment/hand';

test('hand joints leave palm and thumb intact and attach each fingertip independently', () => {
  assert.equal(fingerForPoint(0, -.2), -1);
  assert.equal(fingerForPoint(-.46, .25), -1);
  fingers.forEach((finger, index) => {
    assert.equal(fingerForPoint(finger.x * 1.25, .16 + finger.length), index);
  });
});
