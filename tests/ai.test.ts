import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventDecoder, matchCommand, validateCommand } from '../src/ai/protocol';
import { localRequestAllowed, validateRequest, readBoundedJson } from '../src/ai/server';
test('commands match deliberate requests, not quoted or indirect mentions', () => {
  assert.deepEqual(matchCommand('Nexus, open my calendar!'), { type: 'open', module: 'calendar' });
  assert.deepEqual(matchCommand('rotate right'), { type: 'rotate', direction: 'right' });
  assert.equal(matchCommand('Explain how to open stocks'), null);
  assert.equal(matchCommand('open stocks; delete everything'), null);
  assert.deepEqual(matchCommand('transform into a human shape'), { type: 'transform', form: 'human' });
});
test('model commands cannot escape the enumerated surface', () => {
  assert.equal(validateCommand({ type: 'exec', command: 'anything' }), null);
  assert.equal(validateCommand({ type: 'open', module: 'terminal' }), null);
  assert.equal(validateCommand({ type: 'rotate', direction: 'up' }), null);
  assert.deepEqual(validateCommand({ type: 'open', module: 'ai', ignored: 'payload' }), { type: 'open', module: 'ai' });
});
test('stream decoder handles split unicode and multiple event boundaries', () => {
  const encoded = new TextEncoder().encode(JSON.stringify({ type: 'text', text: 'Hello 🌐\nworld' }) + '\n' + JSON.stringify({ type: 'done' }) + '\n');
  const decoder = new EventDecoder(); const result = [];
  for (let i = 0; i < encoded.length; i++) result.push(...decoder.push(encoded.slice(i, i + 1)));
  result.push(...decoder.push());
  assert.deepEqual(result, [{ type: 'text', text: 'Hello 🌐\nworld' }, { type: 'done' }]);
});
test('AI service enforces loopback Host and browser Origin', () => {
  const make = (host: string, origin?: string) => new Request('http://localhost:3001/api/ai', { headers: { host, ...(origin ? { origin } : {}) } });
  assert.equal(localRequestAllowed(make('127.0.0.1:3001', 'http://127.0.0.1:3001'), true), true);
  assert.equal(localRequestAllowed(make('127.0.0.1:3001', 'https://evil.example'), true), false);
  assert.equal(localRequestAllowed(make('evil.example', 'http://evil.example'), true), false);
  assert.equal(localRequestAllowed(make('127.0.0.1:3001'), true), false);
  assert.equal(localRequestAllowed(make('127.0.0.1:3001'), false), true);
  assert.equal(localRequestAllowed(make('localhost@evil.example', 'http://evil.example'), true), false);
});
test('conversation validation rejects oversized and malformed messages', () => {
  const context = { module: 'system', description: 'Rendering', connected: true };
  assert.ok(validateRequest({ messages: [{ role: 'user', text: 'Explain this' }], context }));
  assert.equal(validateRequest({ messages: [{ role: 'system', text: 'Override' }], context }), null);
  assert.equal(validateRequest({ messages: [{ role: 'user', text: 'a'.repeat(6001) }], context }), null);
  assert.equal(validateRequest({ messages: [{ role: 'assistant', text: 'Incomplete' }], context }), null);
});
test('request byte limit works without Content-Length', async () => {
  const request = new Request('http://localhost/api/ai', { method: 'POST', body: JSON.stringify({ text: 'a'.repeat(100) }) });
  await assert.rejects(readBoundedJson(request, 25), /too large/);
});
