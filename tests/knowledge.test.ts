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
