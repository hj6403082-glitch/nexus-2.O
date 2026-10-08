export type Holding = { id: string; symbol: string; shares: number; cost: number; sector: string };
export type Quote = { price: number; timestamp: number };
export function parseHoldings(raw: string | null): Holding[] {
  if (raw === null) return [];
  const value = JSON.parse(raw);
  if (!Array.isArray(value) || value.length > 20 || !value.every(h => h !== null && typeof h === 'object' && typeof h.id === 'string' && typeof h.symbol === 'string' && /^[A-Z][A-Z0-9.-]{0,14}$/.test(h.symbol) && Number.isFinite(h.shares) && h.shares > 0 && Number.isFinite(h.cost) && h.cost >= 0 && typeof h.sector === 'string')) throw new Error('Saved holdings have an unsupported format.');
  return value;
}
export function portfolioTotals(holdings: Holding[], quotes: Record<string, Quote>) {
  const priced = holdings.filter(h => quotes[h.symbol] && Number.isFinite(quotes[h.symbol].price));
  const value = priced.reduce((sum, h) => sum + quotes[h.symbol].price * h.shares, 0), basis = priced.reduce((sum, h) => sum + h.cost * h.shares, 0);
  const sectors = priced.reduce<Record<string, number>>((totals, h) => ({ ...totals, [h.sector || 'Unclassified']: (totals[h.sector || 'Unclassified'] || 0) + quotes[h.symbol].price * h.shares }), {});
  return { priced, value, basis, sectors };
}
