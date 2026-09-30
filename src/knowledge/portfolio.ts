export type Holding = { id: string; symbol: string; shares: number; cost: number; sector: string };
export type Quote = { price: number; timestamp: number };
export function portfolioTotals(holdings: Holding[], quotes: Record<string, Quote>) {
  const priced = holdings.filter(h => quotes[h.symbol] && Number.isFinite(quotes[h.symbol].price));
  const value = priced.reduce((sum, h) => sum + quotes[h.symbol].price * h.shares, 0), basis = priced.reduce((sum, h) => sum + h.cost * h.shares, 0);
  const sectors = priced.reduce<Record<string, number>>((totals, h) => ({ ...totals, [h.sector || 'Unclassified']: (totals[h.sector || 'Unclassified'] || 0) + quotes[h.symbol].price * h.shares }), {});
  return { priced, value, basis, sectors };
}
