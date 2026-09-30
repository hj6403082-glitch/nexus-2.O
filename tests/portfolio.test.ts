import { test } from 'node:test';
import assert from 'node:assert/strict';
import { portfolioTotals } from '../src/knowledge/portfolio';
test('unpriced holdings are excluded from both valuation and priced cost basis', () => { const result = portfolioTotals([{ id:'1',symbol:'AAA',shares:2,cost:10,sector:'Tech' },{ id:'2',symbol:'BBB',shares:100,cost:500,sector:'Other' }], { AAA: { price:12,timestamp:1 } }); assert.equal(result.value,24); assert.equal(result.basis,20); assert.equal(result.priced.length,1); assert.deepEqual(result.sectors,{Tech:24}); });
test('zero prices are real values, while nonfinite quotes are unavailable', () => { const holding = { id:'1',symbol:'AAA',shares:2,cost:10,sector:'' }; assert.equal(portfolioTotals([holding],{AAA:{price:0,timestamp:1}}).priced.length,1); assert.equal(portfolioTotals([holding],{AAA:{price:NaN,timestamp:1}}).priced.length,0); });
