import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ZenoLink, zenoStatus, zenoToken, zenoUrl, type ZenoSocket } from '../src/ai/zenoBrain';
import { aiProvider } from '../src/ai/ollama';
import { EventDecoder, type StreamEvent } from '../src/ai/protocol';
import type { AIRequest } from '../src/ai/server';

type Frame = Record<string, unknown>;
// Stands in for the brain's chat socket. `reply` scripts what the brain answers to
// each frame the web app sends.
class FakeBrain implements ZenoSocket {
  sent: Frame[] = []; closedWith: number | null = null;
  private listeners: Record<string, ((event: { data?: unknown; code?: number }) => void)[]> = {};
  constructor(public url: string, public headers: Record<string, string>, private reply: (frame: Frame, brain: FakeBrain) => void) {}
  addEventListener(type: string, listener: (event: { data?: unknown; code?: number }) => void) { (this.listeners[type] ??= []).push(listener); }
  emit(type: string, event: { data?: unknown; code?: number } = {}) { for (const listener of this.listeners[type] ?? []) listener(event); }
  push(...frames: Frame[]) { for (const frame of frames) this.emit('message', { data: JSON.stringify(frame) }); }
  open() { this.emit('open'); this.push({ type: 'ready', session: 's1', tools: ['calculate'] }); }
  send(data: string) { const frame = JSON.parse(data); this.sent.push(frame); queueMicrotask(() => this.reply(frame, this)); }
  close(code = 1000) { if (this.closedWith !== null) return; this.closedWith = code; queueMicrotask(() => this.emit('close', { code })); }
  drop(code: number) { this.closedWith = code; this.emit('close', { code }); }
}
function harness(reply: (frame: Frame, brain: FakeBrain) => void, onConnect: (brain: FakeBrain) => void = brain => queueMicrotask(() => brain.open())) {
  const brains: FakeBrain[] = [];
  const link = new ZenoLink({ url: 'http://127.0.0.1:8765', token: () => 'secret-token', connect: (url, headers) => { const brain = new FakeBrain(url, headers, reply); brains.push(brain); onConnect(brain); return brain; } });
  return { link, brains };
}
const ask = (text: string, module = 'orbit'): AIRequest => ({ messages: [{ role: 'user', text: 'earlier' }, { role: 'assistant', text: 'ok' }, { role: 'user', text }], context: { module, description: 'The orbit.', connected: false } });
async function collect(stream: AsyncGenerator<StreamEvent>, onEvent?: (event: StreamEvent) => void | Promise<void>) {
  const events: StreamEvent[] = [];
  for await (const event of stream) { events.push(event); await onEvent?.(event); }
  return events;
}
const answer = (text: string) => (frame: Frame, brain: FakeBrain) => {
  if (frame.type !== 'chat') return;
  const turn = frame.id;
  brain.push({ type: 'thought', turn, step: 1, text: 'Private reasoning.' }, { type: 'tool_call', turn, step: 1, tool: 'open_module', args: { module: 'weather' }, risk: 'read_only' },
    { type: 'command', turn, command: { type: 'open', module: 'weather' } }, { type: 'observation', turn, step: 1, tool: 'open_module', ok: true, content: 'Opened.' },
    { type: 'text', turn, text }, { type: 'done', turn, outcome: 'answered', steps: 2 });
};

test('a message goes to the brain with its token and screen context, and the answer streams back', async () => {
  const { link, brains } = harness(answer('Here is the weather.'));
  const events = await collect(link.turn(ask('show me the weather'), new AbortController().signal));
  assert.deepEqual(events, [{ type: 'command', command: { type: 'open', module: 'weather' } }, { type: 'text', text: 'Here is the weather.' }, { type: 'done' }]);
  const [brain] = brains;
  assert.equal(brain.url, 'ws://127.0.0.1:8765/v1/chat/ws');
  assert.deepEqual(brain.headers, { Authorization: 'Bearer secret-token' });
  assert.equal(brain.sent.length, 1);
  const chat = brain.sent[0];
  // The brain keeps the conversation itself, so only the new message is sent.
  assert.equal(chat.type, 'chat'); assert.equal(chat.text, 'show me the weather');
  assert.deepEqual(JSON.parse(String(chat.context)), { module: 'orbit', description: 'The orbit.', connected: false });
  assert.match(String(chat.id), /^[A-Za-z0-9_.:-]{1,64}$/);
});

test('one connection carries the whole conversation', async () => {
  const { link, brains } = harness(answer('Sure.'));
  await collect(link.turn(ask('first'), new AbortController().signal));
  await collect(link.turn(ask('second'), new AbortController().signal));
  assert.equal(brains.length, 1);
  assert.deepEqual(brains[0].sent.map(f => f.text), ['first', 'second']);
  assert.notEqual(brains[0].sent[0].id, brains[0].sent[1].id);
});

test('a state-changing tool surfaces an approval, and the owner\'s answer resumes the turn', async () => {
  const { link, brains } = harness((frame, brain) => {
    if (frame.type === 'chat') brain.push({ type: 'approval_required', turn: frame.id, step: 1, request_id: 'req-1', tool: 'run_script', args: { name: 'backup' }, risk: 'mutating', thought: 'Back up.', description: 'Run an owner script.', timeout: 120 });
    if (frame.type === 'approval') {
      const turn = brain.sent[0].id;
      brain.push({ type: 'approval', turn, step: 1, request_id: frame.request_id, approved: frame.approved, by: 'owner', reason: '' }, { type: 'text', turn, text: 'Backup done.' }, { type: 'done', turn, outcome: 'answered', steps: 2 });
    }
  });
  const events = await collect(link.turn(ask('back up my files'), new AbortController().signal), event => {
    if (event.type === 'approval') { assert.equal(link.decide('someone-else', true), false); assert.equal(link.decide(event.approval.id, true), true); }
  });
  assert.deepEqual(events, [
    { type: 'approval', approval: { id: 'req-1', tool: 'run_script', description: 'Run an owner script.', args: { name: 'backup' }, timeout: 120 } },
    { type: 'decided', id: 'req-1', approved: true },
    { type: 'text', text: 'Backup done.' }, { type: 'done' },
  ]);
  assert.deepEqual(brains[0].sent[1], { type: 'approval', request_id: 'req-1', approved: true, reason: '' });
  assert.equal(link.decide('req-1', true), false); // already answered
});

test('a denial is sent with its reason', async () => {
  const { link, brains } = harness((frame, brain) => {
    if (frame.type === 'chat') brain.push({ type: 'approval_required', turn: frame.id, step: 1, request_id: 'req-2', tool: 'remember_fact', args: {}, risk: 'mutating', thought: '', description: 'Remember a fact.', timeout: 120 });
    if (frame.type === 'approval') { const turn = brain.sent[0].id; brain.push({ type: 'approval', turn, step: 1, request_id: 'req-2', approved: false, by: 'owner', reason: 'Denied in Zeno.' }, { type: 'text', turn, text: 'Okay, I won\'t.' }, { type: 'done', turn, outcome: 'answered', steps: 2 }); }
  });
  await collect(link.turn(ask('remember this'), new AbortController().signal), event => { if (event.type === 'approval') link.decide(event.approval.id, false); });
  assert.deepEqual(brains[0].sent[1], { type: 'approval', request_id: 'req-2', approved: false, reason: 'Denied in Zeno.' });
});

test('stopping a request cancels the brain\'s turn', async () => {
  const abort = new AbortController();
  const { link, brains } = harness((frame, brain) => {
    if (frame.type === 'chat') { brain.push({ type: 'thought', turn: frame.id, step: 1, text: 'Thinking.' }); abort.abort(); }
    if (frame.type === 'cancel') brain.push({ type: 'done', turn: frame.id, outcome: 'cancelled', steps: 1 });
  });
  const events = await collect(link.turn(ask('long question'), abort.signal));
  assert.deepEqual(events, []);
  assert.deepEqual(brains[0].sent[1], { type: 'cancel', id: brains[0].sent[0].id });
  // The connection survives for the next message.
  assert.equal(brains[0].closedWith, null);
});

test('only commands the web app knows are passed on', async () => {
  const { link } = harness((frame, brain) => {
    if (frame.type !== 'chat') return;
    const turn = frame.id;
    brain.push({ type: 'command', turn, command: { type: 'website', url: 'https://evil.example', label: 'x' } }, { type: 'command', turn, command: { type: 'open', module: 'nowhere' } },
      { type: 'command', turn, command: { type: 'rotate', direction: 'left' } }, { type: 'text', turn, text: 'Done.' }, { type: 'done', turn, outcome: 'answered', steps: 1 });
  });
  assert.deepEqual(await collect(link.turn(ask('spin'), new AbortController().signal)), [{ type: 'command', command: { type: 'rotate', direction: 'left' } }, { type: 'text', text: 'Done.' }, { type: 'done' }]);
});

test('frames from another turn are ignored', async () => {
  const { link } = harness((frame, brain) => {
    if (frame.type !== 'chat') return;
    brain.push({ type: 'text', turn: 'old-turn', text: 'stale' }, { type: 'done', turn: 'old-turn', outcome: 'cancelled', steps: 0 }, { type: 'text', turn: frame.id, text: 'Fresh.' }, { type: 'done', turn: frame.id, outcome: 'answered', steps: 1 });
  });
  assert.deepEqual(await collect(link.turn(ask('hi'), new AbortController().signal)), [{ type: 'text', text: 'Fresh.' }, { type: 'done' }]);
});

test('a second message waits its turn instead of stealing the first one\'s answer', async () => {
  const { link, brains } = harness((frame, brain) => {
    if (frame.type === 'chat') brain.push({ type: 'approval_required', turn: frame.id, step: 1, request_id: 'req-3', tool: 'run_script', args: {}, risk: 'mutating', thought: '', description: 'Run a script.', timeout: 120 });
    if (frame.type === 'approval') { const turn = brain.sent[0].id; brain.push({ type: 'approval', turn, step: 1, request_id: 'req-3', approved: true, by: 'owner', reason: '' }, { type: 'text', turn, text: 'Ran it.' }, { type: 'done', turn, outcome: 'answered', steps: 2 }); }
  });
  const events = await collect(link.turn(ask('run it'), new AbortController().signal), async event => {
    if (event.type !== 'approval') return;
    await assert.rejects(collect(link.turn(ask('meanwhile'), new AbortController().signal)), /still working on your last message/);
    link.decide(event.approval.id, true);
  });
  assert.deepEqual(events.slice(-2), [{ type: 'text', text: 'Ran it.' }, { type: 'done' }]);
  assert.deepEqual(brains[0].sent.map(f => f.type), ['chat', 'approval']);
});

test('a brain error frame ends the turn with its message', async () => {
  const { link } = harness((frame, brain) => { if (frame.type === 'chat') brain.push({ type: 'error', code: 'busy', message: 'Zeno is still working on your last message.' }); });
  await assert.rejects(collect(link.turn(ask('hi'), new AbortController().signal)), /still working on your last message/);
});

test('a brain that goes away mid-answer is reported, and the next message reconnects', async () => {
  let calls = 0;
  const { link, brains } = harness((frame, brain) => {
    if (frame.type !== 'chat') return;
    if (++calls === 1) { brain.push({ type: 'thought', turn: frame.id, step: 1, text: '...' }); brain.drop(1006); return; }
    answer('Back again.')(frame, brain);
  });
  await assert.rejects(collect(link.turn(ask('hi'), new AbortController().signal)), /brain stopped/i);
  const events = await collect(link.turn(ask('hi again'), new AbortController().signal));
  assert.equal(brains.length, 2);
  assert.deepEqual(events.at(-2), { type: 'text', text: 'Back again.' });
});

// A refused handshake reaches the client as a bare error; the brain's status says why.
for (const [name, status, message] of [['bad token', { state: 'ready' }, /token/i], ['still starting', { state: 'starting' }, /starting/i], ['not running', null, /not running/i]] as const) {
  test(`a refused connection (${name}) gets a readable reason`, async () => {
    const statusFetch = async () => status ? Response.json(status) : Promise.reject(new TypeError('fetch failed'));
    const link = new ZenoLink({ url: 'http://127.0.0.1:8765', token: () => 'secret-token', fetch: statusFetch as typeof fetch, connect: (url, headers) => { const brain = new FakeBrain(url, headers, () => {}); queueMicrotask(() => brain.emit('error')); return brain; } });
    await assert.rejects(collect(link.turn(ask('hi'), new AbortController().signal)), message);
  });
}

test('an error on an open connection ends the turn and the next message reconnects', async () => {
  let calls = 0;
  const { link, brains } = harness((frame, brain) => {
    if (frame.type !== 'chat') return;
    if (++calls === 1) { brain.emit('error'); return; }
    answer('Reconnected.')(frame, brain);
  });
  await assert.rejects(collect(link.turn(ask('hi'), new AbortController().signal)), /brain stopped/i);
  assert.deepEqual((await collect(link.turn(ask('hi'), new AbortController().signal))).at(-2), { type: 'text', text: 'Reconnected.' });
  assert.equal(brains.length, 2);
});

test('the brain must answer the handshake in time', async () => {
  const link = new ZenoLink({ url: 'http://127.0.0.1:8765', token: () => 'secret-token', connectTimeout: 20, connect: (url, headers) => new FakeBrain(url, headers, () => {}) });
  await assert.rejects(collect(link.turn(ask('hi'), new AbortController().signal)), /not responding/i);
});

test('without a token the brain is not contacted', async () => {
  let connected = false;
  const link = new ZenoLink({ url: 'http://127.0.0.1:8765', token: () => null, connect: (url, headers) => { connected = true; return new FakeBrain(url, headers, () => {}); } });
  await assert.rejects(collect(link.turn(ask('hi'), new AbortController().signal)), /python -m zeno/);
  assert.equal(connected, false);
});

test('the brain address must stay on this computer', () => {
  const previous = process.env.ZENO_BRAIN_URL;
  try {
    delete process.env.ZENO_BRAIN_URL; assert.equal(zenoUrl(), 'http://127.0.0.1:8765');
    process.env.ZENO_BRAIN_URL = 'http://localhost:9000/'; assert.equal(zenoUrl(), 'http://localhost:9000');
    for (const bad of ['http://192.168.1.5:8765', 'http://example.com', 'file:///etc/passwd', 'not a url', 'http://user:pw@127.0.0.1:8765']) { process.env.ZENO_BRAIN_URL = bad; assert.equal(zenoUrl(), null, bad); }
  } finally { if (previous === undefined) delete process.env.ZENO_BRAIN_URL; else process.env.ZENO_BRAIN_URL = previous; }
});

test('the token comes from the environment, else from the brain\'s token file', () => {
  const saved = { token: process.env.ZENO_API_TOKEN, file: process.env.ZENO_API_TOKEN_FILE };
  const dir = mkdtempSync(join(tmpdir(), 'zeno-')), file = join(dir, 'api-token');
  try {
    delete process.env.ZENO_API_TOKEN; process.env.ZENO_API_TOKEN_FILE = file;
    assert.equal(zenoToken(), null);
    writeFileSync(file, 'from-file\n'); assert.equal(zenoToken(), 'from-file');
    process.env.ZENO_API_TOKEN = ' from-env '; assert.equal(zenoToken(), 'from-env');
  } finally {
    if (saved.token === undefined) delete process.env.ZENO_API_TOKEN; else process.env.ZENO_API_TOKEN = saved.token;
    if (saved.file === undefined) delete process.env.ZENO_API_TOKEN_FILE; else process.env.ZENO_API_TOKEN_FILE = saved.file;
  }
});

test('status reports the brain\'s state in the shape the assistant panel reads', async () => {
  const reply = (body: unknown) => async () => Response.json(body);
  const token = () => 'secret-token';
  const ready = await zenoStatus({ fetch: reply({ state: 'ready', message: '', model: 'qwen3-1.7b.gguf', tools: [], devices: [] }), token });
  assert.deepEqual(ready, { configured: true, provider: 'zeno', state: 'ready', model: 'qwen3-1.7b.gguf', message: 'Zeno brain · qwen3-1.7b.gguf' });
  const starting = await zenoStatus({ fetch: reply({ state: 'starting', message: '', model: 'm.gguf' }), token });
  assert.equal(starting.configured, false); assert.equal(starting.state, 'starting'); assert.match(starting.message, /starting/i);
  const failed = await zenoStatus({ fetch: reply({ state: 'failed', message: 'The model file is missing.', model: '' }), token });
  assert.equal(failed.state, 'failed'); assert.match(failed.message, /The model file is missing\./);
  const offline = await zenoStatus({ fetch: async () => { throw new TypeError('fetch failed'); }, token });
  assert.equal(offline.state, 'offline'); assert.match(offline.message, /python -m zeno/);
  const noToken = await zenoStatus({ fetch: reply({ state: 'ready', message: '', model: 'm.gguf' }), token: () => null });
  assert.equal(noToken.configured, false); assert.match(noToken.message, /token/i);
});

test('AI_PROVIDER=zeno selects the brain', () => {
  const previous = process.env.AI_PROVIDER;
  try { process.env.AI_PROVIDER = 'zeno'; assert.equal(aiProvider(), 'zeno'); }
  finally { if (previous === undefined) delete process.env.AI_PROVIDER; else process.env.AI_PROVIDER = previous; }
});

test('the browser decoder accepts approval events and rejects malformed ones', () => {
  const line = (value: unknown) => new TextEncoder().encode(JSON.stringify(value) + '\n');
  const approval = { id: 'req-1', tool: 'run_script', description: 'Run an owner script.', args: { name: 'backup' }, timeout: 120 };
  assert.deepEqual(new EventDecoder().push(line({ type: 'approval', approval })), [{ type: 'approval', approval }]);
  assert.deepEqual(new EventDecoder().push(line({ type: 'decided', id: 'req-1', approved: false })), [{ type: 'decided', id: 'req-1', approved: false }]);
  for (const bad of [{ type: 'approval', approval: { ...approval, id: 7 } }, { type: 'approval', approval: { ...approval, args: 'x' } }, { type: 'decided', id: 'req-1', approved: 'yes' }]) assert.throws(() => new EventDecoder().push(line(bad)), /Unrecognized/);
});
