import { test } from 'node:test';
import assert from 'node:assert/strict';
import { portfolioTotals } from '../src/knowledge/portfolio';
test('unpriced holdings are excluded from both valuation and priced cost basis', () => { const result = portfolioTotals([{ id:'1',symbol:'AAA',shares:2,cost:10,sector:'Tech' },{ id:'2',symbol:'BBB',shares:100,cost:500,sector:'Other' }], { AAA: { price:12,timestamp:1 } }); assert.equal(result.value,24); assert.equal(result.basis,20); assert.equal(result.priced.length,1); assert.deepEqual(result.sectors,{Tech:24}); });
test('zero prices are real values, while nonfinite quotes are unavailable', () => { const holding = { id:'1',symbol:'AAA',shares:2,cost:10,sector:'' }; assert.equal(portfolioTotals([holding],{AAA:{price:0,timestamp:1}}).priced.length,1); assert.equal(portfolioTotals([holding],{AAA:{price:NaN,timestamp:1}}).priced.length,0); });
import { recordPerformance, performanceSummary } from '../src/knowledge/portfolio';
test('performance keeps one snapshot per day, latest wins, oldest first', () => {
  let h = recordPerformance([], 100, 90, new Date('2026-01-01T09:00:00Z'));
  h = recordPerformance(h, 110, 90, new Date('2026-01-02T09:00:00Z'));
  h = recordPerformance(h, 115, 90, new Date('2026-01-02T16:00:00Z')); // same day replaces
  assert.deepEqual(h.map(p => [p.date, p.value]), [['2026-01-01', 100], ['2026-01-02', 115]]);
  const s = performanceSummary(h)!;
  assert.equal(s.days, 2); assert.equal(s.change, 15); assert.equal(s.percent, 15);
  assert.deepEqual(s.values, [100, 115]);
  assert.equal(performanceSummary(h.slice(0, 1)), null); // one point isn't a curve
});
test('performance caps at a year and drops malformed points', () => {
  const many = Array.from({ length: 400 }, (_, i) => ({ date: `2025-${String((i % 12) + 1).padStart(2, '0')}-${String((i % 28) + 1).padStart(2, '0')}`, value: i, basis: 0 }));
  const h = recordPerformance([...many, { date: 'x', value: NaN, basis: 0 } as never], 500, 400, new Date('2026-06-01T00:00:00Z'));
  assert.ok(h.length <= 365);
  assert.ok(h.every(p => Number.isFinite(p.value)));
});
