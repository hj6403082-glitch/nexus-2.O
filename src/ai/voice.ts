import { voiceSignal } from '@/stores/assistant';
import { createVoiceGraph, fftSignal, VOICE_STYLES, type VoiceGraph, type VoiceStyle } from './audio';
import { SentenceSpeaker } from './speech';

// CinematicSpeaker speaks NEXUS's replies with the neural voice (the local
// Kokoro voice, or ElevenLabs when a key is set) routed through the Web Audio
// graph: the voice character (Ultron-style or natural), sub-bass, spatial
// reverb and the FFT analyser that drives the mouth and the orb. Synthesis of
// the next sentences starts while the current one plays, and the first clause
// is spoken as soon as it arrives, so speech starts quickly and has no gaps.
// If the neural voice is not ready or a request fails, that sentence falls back
// to the browser's best natural voice; the neural voice is retried shortly.
type Item = { text: string; audio: Promise<ArrayBuffer | null> | null };
export class CinematicSpeaker {
  private fallback: SentenceSpeaker;
  private buffer = '';
  private queue: Item[] = [];
  private epoch = 0;
  private playing = false;
  private pumping = false;
  private spokeThisTurn = false;
  private requests = new Set<AbortController>();
  private finishFallback: (() => void) | null = null;
  private context: AudioContext | null = null;
  private graph: VoiceGraph | null = null;
  private graphStyle: VoiceStyle | null = null;
  private source: AudioBufferSourceNode | null = null;
  private raf = 0;
  private neuralRetryAt = 0; // while in the future, skip the neural voice
  private usingFallback = false;

  constructor(private onSpeaking: (speaking: boolean) => void, voiceURI: () => string, private style: () => VoiceStyle = () => 'ultron') {
    this.fallback = new SentenceSpeaker(speaking => {
      this.usingFallback = speaking;
      if (!this.playing) this.onSpeaking(speaking);
      if (!speaking) { const done = this.finishFallback; this.finishFallback = null; done?.(); }
    }, voiceURI, () => this.style());
  }

  get speaking() { return this.pumping || this.playing || this.queue.length > 0 || this.usingFallback; }

  feed(text: string, final = false) {
    this.buffer += text;
    for (;;) {
      const sentence = this.buffer.match(/^([\s\S]*?[.!?])(?:\s+|$)/);
      // Speak the opening clause right away instead of waiting for a full stop.
      const clause = !this.spokeThisTurn && !sentence ? this.buffer.match(/^([\s\S]{16,160}?[,;:—])\s+/) : null;
      if (sentence) { this.enqueue(sentence[1]); this.buffer = this.buffer.slice(sentence[0].length); }
      else if (clause) { this.enqueue(clause[1]); this.buffer = this.buffer.slice(clause[0].length); }
      else if (this.buffer.length > 240) { const end = this.buffer.lastIndexOf(' ', 220); this.enqueue(this.buffer.slice(0, end > 0 ? end : 220)); this.buffer = this.buffer.slice(end > 0 ? end + 1 : 220); }
      else break;
    }
    if (final && this.buffer.trim()) { this.enqueue(this.buffer); this.buffer = ''; }
    if (final) this.spokeThisTurn = false;
    void this.pump();
  }

  private enqueue(sentence: string) {
    const text = sentence.replace(/[`*_#]/g, '').replace(/\s+/g, ' ').trim(); if (!text) return;
    this.spokeThisTurn = true;
    const item: Item = { text, audio: null };
    this.queue.push(item);
    // Pipeline: synthesise up to two sentences ahead of playback.
    this.queue.slice(0, 2).forEach(q => { if (!q.audio) q.audio = this.synthesize(q.text); });
  }

  private synthesize(text: string): Promise<ArrayBuffer | null> | null {
    if (Date.now() < this.neuralRetryAt || typeof AudioContext === 'undefined') return null;
    const abort = new AbortController(); this.requests.add(abort);
    return fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, speed: VOICE_STYLES[this.style()].speed }), signal: abort.signal })
      .then(async response => {
        if (!response.ok) { await response.body?.cancel().catch(() => {}); this.neuralRetryAt = Date.now() + (response.status === 503 ? 15000 : 60000); return null; }
        return response.arrayBuffer();
      })
      .catch(() => null)
      .finally(() => this.requests.delete(abort));
  }

  private async ensureContext(): Promise<boolean> {
    if (typeof AudioContext === 'undefined') return false;
    if (!this.context) { try { this.context = new AudioContext(); } catch { return false; } }
    const style = this.style();
    if (!this.graph || this.graphStyle !== style) { this.graph?.dispose(); this.graph = createVoiceGraph(this.context, style); this.graphStyle = style; }
    if (this.context.state === 'suspended') { try { await this.context.resume(); } catch { /* needs a gesture; fall back */ } }
    return this.context.state === 'running';
  }

  private async pump() {
    if (this.pumping || !this.queue.length) return;
    this.pumping = true;
    const item = this.queue.shift()!;
    const next = this.queue[1]; if (next && !next.audio) next.audio = this.synthesize(next.text);
    if (this.queue[0] && !this.queue[0].audio) this.queue[0].audio = this.synthesize(this.queue[0].text);
    const epoch = this.epoch;
    try {
      const bytes = item.audio ? await item.audio : null;
      if (epoch !== this.epoch) return;
      if (bytes && await this.ensureContext() && this.context && epoch === this.epoch) {
        try {
          const audio = await this.context.decodeAudioData(bytes);
          if (epoch !== this.epoch) return;
          await this.playBuffer(audio, epoch);
          return;
        } catch { /* Undecodable audio: speak this sentence with the browser voice. */ }
      }
      if (epoch !== this.epoch) return;
      await new Promise<void>(resolve => {
        this.finishFallback = resolve;
        this.fallback.feed(item.text, true);
        if (!this.fallback.speaking) { this.finishFallback = null; resolve(); }
      });
    } finally {
      if (epoch === this.epoch) { this.pumping = false; void this.pump(); }
    }
  }

  private playBuffer(audio: AudioBuffer, epoch: number) {
    return new Promise<void>(resolve => {
      if (!this.context || !this.graph) { resolve(); return; }
      const source = this.context.createBufferSource();
      source.buffer = audio; source.playbackRate.value = VOICE_STYLES[this.graphStyle ?? 'natural'].playbackRate; source.connect(this.graph.input);
      this.source = source; this.playing = true; this.onSpeaking(true);
      const loop = () => { if (epoch !== this.epoch) return; this.graph?.update(); voiceSignal.level = fftSignal.level; this.raf = requestAnimationFrame(loop); };
      this.raf = requestAnimationFrame(loop);
      source.onended = () => {
        source.disconnect();
        if (epoch !== this.epoch) { resolve(); return; }
        cancelAnimationFrame(this.raf); voiceSignal.level = 0; fftSignal.level = 0; fftSignal.bands.fill(0);
        this.playing = false; this.source = null;
        if (!this.queue.length) this.onSpeaking(false);
        resolve();
      };
      try { source.start(); } catch { source.onended = null; this.playing = false; resolve(); }
    });
  }

  stop() {
    this.epoch++; this.buffer = ''; this.queue = []; this.playing = false; this.pumping = false; this.spokeThisTurn = false;
    this.requests.forEach(r => r.abort()); this.requests.clear();
    const finish = this.finishFallback; this.finishFallback = null; finish?.();
    if (this.raf) cancelAnimationFrame(this.raf); this.raf = 0; voiceSignal.level = 0; fftSignal.level = 0; fftSignal.bands.fill(0);
    try { this.source?.stop(); } catch { /* already stopped */ } this.source = null;
    this.fallback.stop();
    this.onSpeaking(false);
  }
}
