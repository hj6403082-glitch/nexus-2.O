import { test } from 'node:test';
import assert from 'node:assert/strict';
import { grokEvents, streamGrok } from '../src/ai/grok';
function body(items: unknown[], done = true) {
  const wire = items.map(item => `data: ${JSON.stringify(item)}\r\n\r\n`).join('') + (done ? 'data: [DONE]\r\n\r\n' : '');
  const bytes = new TextEncoder().encode(wire);
  return new ReadableStream<Uint8Array>({ start(c) { for (const byte of bytes) c.enqueue(Uint8Array.of(byte)); c.close(); } });
}
const text = (content: string) => ({ choices: [{ delta: { content } }] });
const call = (name: string, args: string) => ({ choices: [{ delta: { tool_calls: [{ index: 0, function: { name, arguments: args } }] } }] });
test('Grok handles byte-split Unicode and SSE boundaries and only emits public text', async () => {
  const result = await Array.fromAsync(grokEvents(body([text('Hello 🌐'), { choices: [{ delta: { reasoning_content: 'private' } }] }])));
  assert.deepEqual(result, [{ type: 'text', text: 'Hello 🌐' }, { type: 'done' }]);
});
test('Grok accumulates tool arguments and validates before dispatch', async () => {
  const result = await Array.fromAsync(grokEvents(body([call('transform_form', '{"form":'), call('', '"human"}')])));
  assert.deepEqual(result, [{ type: 'command', command: { type: 'transform', form: 'human' } }, { type: 'done' }]);
});
test('Grok rejects truncated streams and never dispatches their pending actions', async () => {
  const events: unknown[] = [];
  await assert.rejects(async () => { for await (const e of grokEvents(body([call('navigate', '{"type":"close"}')], false))) events.push(e); }, /ended early/);
  assert.deepEqual(events, []);
});
test('Grok ignores unknown tools and forbidden commands', async () => {
  for (const item of [call('exec', '{"command":"bad"}'), call('navigate', '{"type":"website","url":"https://example.com"}'), call('navigate', 'invalid')]) {
    assert.deepEqual(await Array.fromAsync(grokEvents(body([text('OK'), item]))), [{ type: 'text', text: 'OK' }, { type: 'done' }]);
  }
});
test('Grok turns provider failures into safe errors without leaking response bodies', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('sensitive provider detail', { status: 401 });
    await assert.rejects(async () => { for await (const event of streamGrok({ messages: [{ role: 'user', text: 'hi' }], context: { module: 'orbit', description: '', connected: false } }, new AbortController().signal)) void event; }, /Grok rejected the key/);
  } finally { globalThis.fetch = original; }
});
