// Launcher ranking: prefix first, then initials, then a word boundary, then a substring.
export function rank(name: string, query: string) {
  const n = name.toLowerCase(), q = query.toLowerCase().trim();
  if (!q) return 0;
  if (n.startsWith(q)) return 1;
  const words = n.split(/[\s\-_.]+/).filter(Boolean);
  if (q.length > 1 && words.map(w => w[0]).join('').startsWith(q.replace(/\s+/g, ''))) return 2;
  if (words.some(w => w.startsWith(q))) return 3;
  return n.includes(q) ? 4 : 99;
}
// Stable sort by rank, keeping each source's own order within a rank.
export function rankEntries<T extends { name: string }>(entries: T[], query: string) {
  return entries.map((entry, order) => ({ entry, order, score: rank(entry.name, query) })).filter(e => e.score < 99).sort((a, b) => a.score - b.score || a.order - b.order).map(e => e.entry);
}
