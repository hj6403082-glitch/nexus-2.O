import test from 'node:test';
import assert from 'node:assert/strict';
import { parseEntries } from '../src/knowledge/entries';
test('unreadable saved collections fail without silently replacing data with an empty collection', () => {
  for (const raw of ['{', '{}', '[null]', '[{"id":"1","title":"Preserve me"}]']) assert.throws(() => parseEntries(raw));
  assert.deepEqual(parseEntries(null), []);
  const entries = [{ id: '1', title: 'Project', detail: 'My notes' }];
  assert.deepEqual(parseEntries(JSON.stringify(entries)), entries);
});
