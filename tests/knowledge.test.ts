import { test } from 'node:test';
import assert from 'node:assert/strict';
import { followerHistory, instagramTarget } from '../src/knowledge/providers';
test('Instagram token routing distinguishes both login methods', () => {
  assert.deepEqual(instagramTarget('IGAA_example'), { base: 'https://graph.instagram.com', account: 'me' });
  assert.deepEqual(instagramTarget('EAA_example', '123'), { base: 'https://graph.facebook.com', account: '123' });
  assert.throws(() => instagramTarget('EAA_example'));
  assert.throws(() => instagramTarget('unknown'));
});
test('follower deltas back-accumulate from the observed total', () => {
  assert.deepEqual(followerHistory(100, [{ date: '2026-01-01', delta: 4 }, { date: '2026-01-02', delta: -2 }, { date: '2026-01-03', delta: 5 }]), [{ date: '2026-01-01', total: 97 }, { date: '2026-01-02', total: 95 }, { date: '2026-01-03', total: 100 }]);
});
test('Instagram insights parse daily follower deltas and reach', async () => {
  const { parseInsights, engagement } = await import('../src/knowledge/providers');
  const parsed = parseInsights({ data: [{ name: 'follower_count', values: [{ value: 3, end_time: '2026-10-01T07:00:00+0000' }, { value: -1, end_time: '2026-10-02T07:00:00+0000' }] }, { name: 'reach', values: [{ value: 900, end_time: '2026-10-01T07:00:00+0000' }] }] });
  assert.deepEqual(parsed.deltas, [{ date: '2026-10-01', delta: 3 }, { date: '2026-10-02', delta: -1 }]);
  assert.deepEqual(followerHistory(500, parsed.deltas), [{ date: '2026-10-01', total: 501 }, { date: '2026-10-02', total: 500 }]);
  assert.deepEqual(parsed.reach, [{ date: '2026-10-01', value: 900 }]);
  assert.deepEqual(engagement([{ id: 'a', like_count: 10 }, { id: 'b', like_count: 40, comments_count: 10 }], 1000), { rate: 0.03, top: ['b', 'a'] });
});
