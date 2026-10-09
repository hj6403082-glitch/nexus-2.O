export type Holding = { id: string; symbol: string; shares: number; cost: number; sector: string };
export type Quote = { price: number; timestamp: number };
export function portfolioTotals(holdings: Holding[], quotes: Record<string, Quote>) {
  const priced = holdings.filter(h => quotes[h.symbol] && Number.isFinite(quotes[h.symbol].price));
  const value = priced.reduce((sum, h) => sum + quotes[h.symbol].price * h.shares, 0), basis = priced.reduce((sum, h) => sum + h.cost * h.shares, 0);
  const sectors = priced.reduce<Record<string, number>>((totals, h) => ({ ...totals, [h.sector || 'Unclassified']: (totals[h.sector || 'Unclassified'] || 0) + quotes[h.symbol].price * h.shares }), {});
  return { priced, value, basis, sectors };
}

export type PerformancePoint = { date: string; value: number; basis: number };
// Portfolio performance is reconstructed from local daily snapshots: one point
// per calendar day (the latest wins), oldest first, capped to a year. No
// brokerage history is fetched; this is the record of what NEXUS has observed.
export function recordPerformance(history: PerformancePoint[], value: number, basis: number, at = new Date()): PerformancePoint[] {
  const date = at.toISOString().slice(0, 10);
  const prior = history.filter(p => typeof p.date === 'string' && Number.isFinite(p.value) && Number.isFinite(p.basis) && p.date !== date);
  return [...prior, { date, value, basis }].sort((a, b) => a.date.localeCompare(b.date)).slice(-365);
}
export function performanceSummary(history: PerformancePoint[]) {
  if (history.length < 2) return null;
  const first = history[0], last = history[history.length - 1];
  const change = last.value - first.value;
  return { days: history.length, startValue: first.value, endValue: last.value, change, percent: first.value > 0 ? change / first.value * 100 : null, values: history.map(p => p.value) };
}
