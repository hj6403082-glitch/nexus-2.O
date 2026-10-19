// Turns a set of surface points into a net: each node is tied to its nearest
// neighbours (within reach), giving an even mesh of short threads across the
// face. Returns line-segment index pairs, each edge once.
export function buildNet(positions: Float32Array, nodes: number[], neighbours = 4, reach = .05): Uint32Array {
  const cell = reach, inv = 1 / cell, grid = new Map<number, number[]>();
  const key = (x: number, y: number, z: number) => ((x + 512) * 1024 + (y + 512)) * 1024 + (z + 512);
  for (const n of nodes) {
    const k = key(Math.floor(positions[n * 3] * inv), Math.floor(positions[n * 3 + 1] * inv), Math.floor(positions[n * 3 + 2] * inv));
    const list = grid.get(k); if (list) list.push(n); else grid.set(k, [n]);
  }
  const seen = new Set<number>(), edges: number[] = [], reach2 = reach * reach;
  for (const a of nodes) {
    const ax = positions[a * 3], ay = positions[a * 3 + 1], az = positions[a * 3 + 2];
    const gx = Math.floor(ax * inv), gy = Math.floor(ay * inv), gz = Math.floor(az * inv);
    const near: [number, number][] = [];
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
      for (const b of grid.get(key(gx + dx, gy + dy, gz + dz)) ?? []) {
        if (b === a) continue;
        const ex = positions[b * 3] - ax, ey = positions[b * 3 + 1] - ay, ez = positions[b * 3 + 2] - az, d = ex * ex + ey * ey + ez * ez;
        if (d <= reach2) near.push([d, b]);
      }
    }
    near.sort((p, q) => p[0] - q[0]);
    for (const [, b] of near.slice(0, neighbours)) {
      const lo = Math.min(a, b), hi = Math.max(a, b), id = lo * 1048576 + hi;
      if (!seen.has(id)) { seen.add(id); edges.push(lo, hi); }
    }
  }
  return Uint32Array.from(edges);
}
