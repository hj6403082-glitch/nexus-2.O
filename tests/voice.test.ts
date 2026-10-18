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
test('neural voice synthesises at most two sentences ahead and stop aborts them all', async () => {
  const original = globalThis.fetch, audioContext = (globalThis as { AudioContext?: unknown }).AudioContext;
  const signals: AbortSignal[] = [];
  (globalThis as { AudioContext?: unknown }).AudioContext = class {};
  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    const signal = init!.signal!; signals.push(signal);
    signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  const speaker = new CinematicSpeaker(() => {}, () => '');
  try {
    speaker.feed('First. Second. Third. Fourth.'); await tick();
    assert.ok(signals.length >= 2 && signals.length <= 3, `in flight: ${signals.length}`);
    const cancel = globalThis.cancelAnimationFrame;
    globalThis.cancelAnimationFrame = () => {};
    try { speaker.stop(); } finally { globalThis.cancelAnimationFrame = cancel; }
    await tick(); assert.ok(signals.every(s => s.aborted)); assert.equal(speaker.speaking, false);
  } finally { globalThis.fetch = original; (globalThis as { AudioContext?: unknown }).AudioContext = audioContext; }
});
test('the opening clause is spoken before the sentence ends', async () => {
  const spoken: { text: string }[] = [];
  const originals = { utterance: globalThis.SpeechSynthesisUtterance, speech: globalThis.speechSynthesis };
  Object.assign(globalThis, { SpeechSynthesisUtterance: class { constructor(public text: string) {} }, speechSynthesis: { getVoices: () => [], speak: (u: { text: string }) => spoken.push(u), cancel: () => {} } });
  const speaker = new CinematicSpeaker(() => {}, () => '');
  try { speaker.feed('The answer is simple, and it starts right here'); await tick(); assert.equal(spoken[0]?.text, 'The answer is simple,'); }
  finally { speaker.stop(); Object.assign(globalThis, { SpeechSynthesisUtterance: originals.utterance, speechSynthesis: originals.speech }); }
});
