import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildNet } from '../src/embodiment/net';
test('the face net ties each node to its nearest neighbours once', () => {
  // A 10x10 grid of nodes 0.01 apart, plus one far-away point.
  const positions = new Float32Array(101 * 3);
  for (let i = 0; i < 100; i++) positions.set([(i % 10) * .01, Math.floor(i / 10) * .01, 0], i * 3);
  positions.set([5, 5, 5], 100 * 3);
  const nodes = Array.from({ length: 101 }, (_, i) => i), edges = buildNet(positions, nodes, 4, .012);
  const pairs = new Set<string>();
  for (let i = 0; i < edges.length; i += 2) {
    const a = edges[i], b = edges[i + 1]; assert.ok(a < b); pairs.add(`${a}-${b}`);
    const d = Math.hypot(positions[a * 3] - positions[b * 3], positions[a * 3 + 1] - positions[b * 3 + 1]);
    assert.ok(d < .0101, 'only neighbouring nodes are joined');
  }
  assert.equal(pairs.size, edges.length / 2);
  assert.equal(pairs.size, 180); // every horizontal and vertical neighbour on the grid
  assert.ok(![...pairs].some(p => p.split('-').includes('100')), 'an isolated point gets no threads');
});
