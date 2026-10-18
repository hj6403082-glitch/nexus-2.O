import { test } from 'node:test';
import assert from 'node:assert/strict';
import { companionNotes, emptyMemory, greeting, learn, readMood } from '../src/ai/companion';
import { validateRequest } from '../src/ai/server';
test('Zeno learns a name and explicit memories, and answers locally', () => {
  let r = learn('Hey Zeno, call me boss', emptyMemory());
  assert.equal(r.memory.name, 'Boss'); assert.match(r.reply!, /Boss/);
  r = learn('remember that my dog is called Max.', r.memory);
  assert.deepEqual(r.memory.facts, ['my dog is called Max']); assert.ok(r.reply);
  r = learn('what do you remember about me?', r.memory);
  assert.match(r.reply!, /your name's Boss and your dog is called Max/);
  r = learn('forget about max', r.memory);
  assert.deepEqual(r.memory.facts, []); assert.equal(r.memory.name, 'Boss');
  assert.equal(learn('forget everything', r.memory).memory.name, null);
});
test('ordinary messages teach quietly and still go to the model', () => {
  const r = learn('I really love space documentaries, but I hate spiders. What should I watch?', emptyMemory());
  assert.equal(r.reply, null); assert.deepEqual(r.memory.facts, ['I love space documentaries', 'I hate spiders']);
  assert.equal(learn('I like it', emptyMemory()).memory.facts.length, 0);
  assert.equal(learn('open system', emptyMemory()).reply, null);
});
test('mood, notes and greetings are personal and time-aware', () => {
  assert.equal(readMood('ugh this is not working'), 'frustrated'); assert.equal(readMood('rough day honestly'), 'down'); assert.equal(readMood('I did it!!'), 'excited'); assert.equal(readMood('what is MCP'), null);
  const evening = new Date(2026, 9, 18, 19, 30), memory = { name: 'Boss', facts: ['I love F1'], lastChatAt: evening.getTime() - 3 * 3600000, chats: 4 };
  const notes = companionNotes(memory, evening, 'excited');
  assert.match(notes, /name is Boss/); assert.match(notes, /I love F1/); assert.match(notes, /evening/); assert.match(notes, /3 hours ago/); assert.match(notes, /excited/);
  assert.equal(greeting(memory, evening).title, 'Evening, Boss!');
  assert.match(greeting(emptyMemory(), evening).title, /I'm Zeno/);
});
test('companion notes are accepted as bounded optional context', () => {
  const context = { module: 'orbit', description: 'Orbit', connected: false };
  assert.equal(validateRequest({ messages: [{ role: 'user', text: 'hi' }], context: { ...context, companion: 'The user is Boss.' } })?.context.companion, 'The user is Boss.');
  assert.equal(validateRequest({ messages: [{ role: 'user', text: 'hi' }], context: { ...context, companion: 'x'.repeat(1501) } }), null);
  assert.equal(validateRequest({ messages: [{ role: 'user', text: 'hi' }], context })?.context.companion, undefined);
});
test('the owner profile seeds memory and survives what Zeno learns', async () => {
  const { applyProfile, parseProfile } = await import('../src/ai/companion');
  const profile = parseProfile({ name: 'Boss', facts: ['I love robotics.', 42, '  '] });
  assert.deepEqual(profile, { name: 'Boss', facts: ['I love robotics'] });
  const memory = applyProfile({ name: 'Sam', facts: ['I love F1', 'i love robotics'], lastChatAt: 5, chats: 2 }, profile);
  assert.deepEqual(memory, { name: 'Boss', facts: ['I love robotics', 'I love F1'], lastChatAt: 5, chats: 2 });
  assert.match(companionNotes(memory, new Date(2026, 9, 18, 9), null), /call them Boss/);
  assert.equal(applyProfile(memory, parseProfile(null)), memory);
});
