import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CinematicSpeaker } from '../src/ai/voice';
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
test('browser voice drains long sentences and final unpunctuated text in order', async () => {
  const spoken: { text: string; onend?: () => void }[] = [];
  const originals = { utterance: globalThis.SpeechSynthesisUtterance, speech: globalThis.speechSynthesis };
  Object.assign(globalThis, { SpeechSynthesisUtterance: class { constructor(public text: string) {} }, speechSynthesis: { getVoices: () => [], speak: (u: { text: string }) => spoken.push(u), cancel: () => {} } });
  const speaker = new CinematicSpeaker(() => {}, () => '');
  try {
    speaker.feed('First sentence. Second sentence. Final words', true);
    await tick(); assert.equal(spoken.length, 1);
    // Completion, not a 400ms timer, advances the queue.
    spoken[0].onend?.(); await tick(); assert.equal(spoken[1]?.text, 'Second sentence.');
    spoken[1].onend?.(); await tick(); assert.equal(spoken[2]?.text, 'Final words');
    spoken[2].onend?.(); await tick(); assert.equal(speaker.speaking, false);
  } finally { speaker.stop(); Object.assign(globalThis, { SpeechSynthesisUtterance: originals.utterance, speechSynthesis: originals.speech }); }
});
test('premium fetches serialize and stop aborts an in-flight synthesis', async () => {
  const original = globalThis.fetch;
  const signals: AbortSignal[] = [];
  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    const signal = init!.signal!; signals.push(signal);
    signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  const speaker = new CinematicSpeaker(() => {}, () => '');
  Object.assign(speaker, { ensureContext: async () => true });
  try {
    speaker.feed('First.'); await tick(); speaker.feed('Second.'); await tick();
    assert.equal(signals.length, 1);
    // Stop is safe even without a browser RAF implementation in this test.
    const cancel = globalThis.cancelAnimationFrame;
    globalThis.cancelAnimationFrame = () => {};
    try { speaker.stop(); } finally { globalThis.cancelAnimationFrame = cancel; }
    await tick(); assert.equal(signals[0].aborted, true); assert.equal(speaker.speaking, false);
  } finally { globalThis.fetch = original; }
});
