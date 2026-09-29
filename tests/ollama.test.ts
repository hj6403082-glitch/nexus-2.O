import { test } from 'node:test';
import assert from 'node:assert/strict';
import { streamOllama } from '../src/ai/ollama';
test('local model streams split UTF-8 and validates transformation tools', async () => {
  const original = globalThis.fetch; const previous = process.env.OLLAMA_MODEL; process.env.OLLAMA_MODEL = 'test:local';
  globalThis.fetch = async input => {
    if (String(input).endsWith('/api/tags')) return Response.json({ models: [{ name: 'test:local' }] });
    assert.equal(String(input), 'http://127.0.0.1:11434/api/chat');
    const encoded = new TextEncoder().encode(JSON.stringify({ message: { content: 'Hello 🌐', tool_calls: [{ function: { name: 'transform_form', arguments: { form: 'human' } } }] }, done: true }) + '\n');
    return new Response(new ReadableStream({ start(controller) { for (const byte of encoded) controller.enqueue(new Uint8Array([byte])); controller.close(); } }));
  };
  try { const output = []; for await (const item of streamOllama({ messages: [{ role: 'user', text: 'Hello' }], context: { module: 'orbit', description: '', connected: false } }, new AbortController().signal)) output.push(item); assert.deepEqual(output, [{ type: 'text', text: 'Hello 🌐' }, { type: 'command', command: { type: 'transform', form: 'human' } }, { type: 'done' }]); }
  finally { globalThis.fetch = original; if (previous === undefined) delete process.env.OLLAMA_MODEL; else process.env.OLLAMA_MODEL = previous; }
});
