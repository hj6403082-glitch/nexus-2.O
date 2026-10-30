import test from 'node:test';
import assert from 'node:assert/strict';
import { estimateGaze, gazeTarget, type FacePoint } from '../src/embodiment/gaze';

// A frontal face built from the FaceMesh indices estimateGaze reads, centred
// at (cx, cy) in normalised, unmirrored image space.
function face(cx: number, cy: number, noseShift = 0): FacePoint[] {
  const points: FacePoint[] = Array.from({ length: 478 }, () => ({ x: cx, y: cy }));
  points[33] = { x: cx - .08, y: cy };            // outer eye corners
  points[263] = { x: cx + .08, y: cy };
  points[1] = { x: cx + noseShift, y: cy + .072 }; // nose tip
  points[10] = { x: cx, y: cy - .15 };            // forehead
  points[152] = { x: cx, y: cy + .25 };           // chin
  return points;
}

test('estimateGaze needs a full face mesh', () => {
  assert.equal(estimateGaze(face(.5, .4).slice(0, 100)), null);
});

test('a centred, frontal face holds NEXUS looking straight ahead', () => {
  const g = estimateGaze(face(.5, .4))!;
  const t = gazeTarget(g);
  assert.ok(Math.abs(t.yaw) < .05, `yaw ${t.yaw}`);
  assert.ok(Math.abs(t.pitch) < .05, `pitch ${t.pitch}`);
});

test('NEXUS follows the user across the frame', () => {
  // The camera image is unmirrored: a user moving to their left appears at
  // larger x, and NEXUS should turn toward screen-left (negative yaw).
  assert.ok(gazeTarget(estimateGaze(face(.75, .4))!).yaw < -.4);
  assert.ok(gazeTarget(estimateGaze(face(.25, .4))!).yaw > .4);
  // Lower in frame → look down (positive pitch); higher → look up.
  assert.ok(gazeTarget(estimateGaze(face(.5, .6))!).pitch > .3);
  assert.ok(gazeTarget(estimateGaze(face(.5, .2))!).pitch < -.3);
});

test('a head turn nudges the neck but position dominates', () => {
  const still = gazeTarget(estimateGaze(face(.5, .4))!).yaw;
  const turned = gazeTarget(estimateGaze(face(.5, .4, .04))!).yaw;
  assert.ok(turned < still && turned > -.5, `turned ${turned}`);
});
