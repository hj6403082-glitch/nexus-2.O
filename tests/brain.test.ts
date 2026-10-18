import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ollamaStatus, pullOllama, resetOllamaCache, trimHistory, resolveModel, streamOllama, ThinkFilter, validModelName } from '../src/ai/ollama';
import { EventDecoder } from '../src/ai/protocol';

const input = { messages: [{ role: 'user' as const, text: 'Hello' }], context: { module: 'orbit', description: '', connected: false } };
const lines = (...items: unknown[]) => new Response(items.map(i => typeof i === 'string' ? i : JSON.stringify(i)).join('\n') + '\n');
async function withOllama(handler: (url: string, body: Record<string, unknown> | null) => Response | Promise<Response>, run: () => Promise<void>, model: string | undefined = 'test:local') {
  const original = globalThis.fetch, previous = process.env.OLLAMA_MODEL;
  if (model === undefined) delete process.env.OLLAMA_MODEL; else process.env.OLLAMA_MODEL = model;
  resetOllamaCache();
  globalThis.fetch = async (url, init) => handler(String(url), init?.body ? JSON.parse(String(init.body)) : null);
  try { await run(); } finally { globalThis.fetch = original; if (previous === undefined) delete process.env.OLLAMA_MODEL; else process.env.OLLAMA_MODEL = previous; }
}
const collect = async () => { const out = []; for await (const e of streamOllama(input, new AbortController().signal)) out.push(e); return out; };

test('model names match with or without the implicit latest tag', () => {
  assert.equal(resolveModel(['qwen3:latest'], 'qwen3'), 'qwen3:latest');
  assert.equal(resolveModel(['qwen3'], 'qwen3:latest'), 'qwen3');
  assert.equal(resolveModel(['qwen3:4b'], 'qwen3:1.7b'), '');
  assert.equal(resolveModel(['a', 'b'], ''), 'a');
});
test('brain status distinguishes offline, empty, missing and ready', async () => {
  await withOllama(() => { throw new TypeError('fetch failed'); }, async () => assert.equal((await ollamaStatus()).state, 'offline'));
  await withOllama(() => Response.json({ models: [] }), async () => { const s = await ollamaStatus(); assert.equal(s.state, 'no-model'); assert.equal(s.configured, false); });
  await withOllama(() => Response.json({ models: [{ name: 'llama3.2:latest' }] }), async () => { const s = await ollamaStatus(); assert.equal(s.state, 'model-missing'); assert.equal(s.configured, true); assert.equal(s.model, 'llama3.2:latest'); assert.equal(s.wanted, 'test:local'); });
  await withOllama(() => Response.json({ models: [{ name: 'test:local' }, { name: 'big:cloud' }] }), async () => { const s = await ollamaStatus(); assert.equal(s.state, 'ready'); assert.deepEqual(s.models, ['test:local']); });
  await withOllama(() => new Response('not json'), async () => assert.equal((await ollamaStatus()).state, 'no-model'));
});
test('a model without tool support is retried as plain chat', async () => {
  const bodies: Record<string, unknown>[] = [];
  await withOllama((url, body) => {
    if (url.endsWith('/api/tags')) return Response.json({ models: [{ name: 'test:local' }] });
    bodies.push(body!);
    return body!.tools ? new Response(JSON.stringify({ error: 'test:local does not support tools' }), { status: 400 }) : lines({ message: { content: 'Plain answer' }, done: true });
  }, async () => {
    assert.deepEqual(await collect(), [{ type: 'text', text: 'Plain answer' }, { type: 'done' }]);
    assert.equal(bodies.length, 2); assert.equal(bodies[1].tools, undefined); assert.equal(bodies[1].think, undefined);
  });
});
test('leaked reasoning is removed even when tags split across chunks', () => {
  const f = new ThinkFilter();
  const out = ['Hi <thi', 'nk>secret plan</th', 'ink> there', ' <', 'b>'].map(c => f.push(c)).join('') + f.flush();
  assert.equal(out, 'Hi  there <b>');
});
test('stream failures become readable errors, never raw exceptions', async () => {
  const tags = Response.json({ models: [{ name: 'test:local' }] });
  const cases: [() => Response, RegExp][] = [
    [() => lines('{"message":{"content":"Hi"}', 'garbage{'), /unreadable response/],
    [() => lines({ error: 'CUDA out of memory' }), /ran out of memory/],
    [() => lines({ message: { content: 'Half' } }), /ended early/],
    [() => lines({ message: { content: '' }, done: true }), /empty answer/],
    [() => new Response('model "x" not found', { status: 404 }), /not downloaded/],
    [() => new Response('boom', { status: 500 }), /model error/],
    [() => new Response(new ReadableStream({ pull(c) { c.error(new TypeError('terminated')); } })), /stopped mid-answer/],
  ];
  for (const [chat, pattern] of cases) await withOllama(url => url.endsWith('/api/tags') ? tags.clone() : chat(), async () => { await assert.rejects(collect(), pattern); });
  await withOllama(url => { if (url.endsWith('/api/tags')) return tags.clone(); throw new TypeError('fetch failed'); }, async () => { await assert.rejects(collect(), /stopped responding/); });
  await withOllama(() => { throw new TypeError('fetch failed'); }, async () => { await assert.rejects(collect(), /not running/); });
});
test('model downloads report progress and reject bad names', async () => {
  assert.equal(validModelName('qwen3:1.7b'), true); assert.equal(validModelName('hf.co/org/model:Q4_K_M'), true);
  assert.equal(validModelName('../etc'), false); assert.equal(validModelName('a b'), false); assert.equal(validModelName(''), false);
  await withOllama(() => lines({ status: 'pulling manifest' }, { status: 'downloading', completed: 50, total: 100 }, { status: 'success' }), async () => {
    const out = []; for await (const p of pullOllama('qwen3:1.7b', new AbortController().signal)) out.push(p);
    assert.deepEqual(out.at(1), { status: 'downloading', completed: 50, total: 100 }); assert.equal(out.at(-1)?.status, 'success');
  });
  await withOllama(() => lines({ status: 'downloading', completed: 1, total: 100 }), async () => { await assert.rejects((async () => { for await (const _ of pullOllama('qwen3:1.7b', new AbortController().signal)) void _; })(), /stopped before/); });
  await withOllama(() => lines({ error: 'pull model manifest: file does not exist' }), async () => { await assert.rejects((async () => { for await (const _ of pullOllama('nope', new AbortController().signal)) void _; })(), /could not find/); });
});
test('a garbled browser stream line is reported plainly', () => {
  const decoder = new EventDecoder();
  assert.throws(() => decoder.push(new TextEncoder().encode('<html>\n')), /garbled/);
  assert.throws(() => new EventDecoder().push(new TextEncoder().encode('null\n')), /Unrecognized/);
});
test('only recent turns are sent to the local model, starting with the user', () => {
  const many = Array.from({ length: 20 }, (_, i) => ({ role: (i % 2 ? 'assistant' : 'user') as 'user' | 'assistant', text: `m${i}` }));
  const out = trimHistory(many); assert.ok(out.length <= 10); assert.equal(out[0].role, 'user'); assert.equal(out.at(-1)?.text, 'm19');
  assert.equal(trimHistory([{ role: 'user', text: 'x'.repeat(9000) }]).length, 1);
});
test('the system prompt is identical across turns so Ollama can reuse its cache', async () => {
  const systems: string[] = [];
  await withOllama((url, body) => {
    if (url.endsWith('/api/tags')) return Response.json({ models: [{ name: 'test:local' }] });
    systems.push((body!.messages as { content: string }[])[0].content); assert.equal(body!.keep_alive, '30m');
    return lines({ message: { content: 'ok' }, done: true });
  }, async () => {
    for (const module of ['orbit', 'system']) for await (const _ of streamOllama({ ...input, context: { module, description: module, connected: false } }, new AbortController().signal)) void _;
  });
  assert.equal(systems.length, 2); assert.equal(systems[0], systems[1]);
});
