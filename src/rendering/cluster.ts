// When cards are grouped, they leave the orbit and settle into a tidy grid in
// front of the user. Pure geometry so the layout is testable and stable: the
// same member set always lands in the same slots (split is the orbit spring
// running in reverse, never a second animation).
export type Vec3 = [number, number, number];
export function clusterTarget(rank: number, total: number): Vec3 {
  const columns = Math.min(5, Math.max(1, total));
  const rows = Math.ceil(total / columns);
  const col = rank % columns, row = Math.floor(rank / columns);
  const spanX = 1.75, spanY = 2.05;
  // Centre the grid on the orbit's focal point, lifted to eye level and pulled
  // a little nearer than the orbit radius so the group reads as "brought in".
  const x = (col - (columns - 1) / 2) * spanX;
  const y = ((rows - 1) / 2 - row) * spanY + .2;
  return [x, y, -1.4];
}
export function clusterMembers(selected: readonly string[], all: readonly string[]) {
  // Multi-select drives the group when the user has chosen cards; otherwise the
  // whole orbit gathers.
  const chosen = selected.filter(id => all.includes(id));
  return chosen.length ? all.filter(id => chosen.includes(id)) : [...all];
}
