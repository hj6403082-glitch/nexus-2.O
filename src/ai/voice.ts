import { voiceSignal } from '@/stores/assistant';
import { createVoiceGraph, fftSignal, type VoiceGraph } from './audio';
import { SentenceSpeaker } from './speech';

// CinematicSpeaker is a drop-in replacement for SentenceSpeaker that prefers the
// premium NEXUS voice (ElevenLabs via /api/tts) routed through the Web Audio
// cinematic graph — sub-bass, spatial reverb, and the FFT analyser that drives
// the humanoid's face. If the premium voice is not configured, or a request
// fails, it transparently falls back to the browser's speech synthesis (the
// existing SentenceSpeaker), sentence by sentence. The public surface matches
// SentenceSpeaker so the controller is unchanged.
export class CinematicSpeaker {
  private fallback: SentenceSpeaker;
  private buffer = '';
  private queue: string[] = [];
  private epoch = 0;
  private playing = false;
  private pumping = false;
  private request: AbortController | null = null;
  private finishFallback: (() => void) | null = null;
  private context: AudioContext | null = null;
  private graph: VoiceGraph | null = null;
  private source: AudioBufferSourceNode | null = null;
  private raf = 0;
  private premium: boolean | null = null; // null = unknown, probe lazily
  private usingFallback = false;

  constructor(private onSpeaking: (speaking: boolean) => void, voiceURI: () => string) {
    this.fallback = new SentenceSpeaker(speaking => {
      this.usingFallback = speaking;
      if (!this.playing) this.onSpeaking(speaking);
      if (!speaking) { const done = this.finishFallback; this.finishFallback = null; done?.(); }
    }, voiceURI);
  }

  get speaking() { return this.pumping || this.playing || this.queue.length > 0 || this.usingFallback; }

  feed(text: string, final = false) {
    this.buffer += text;
    for (;;) {
      const sentence = this.buffer.match(/^([\s\S]*?[.!?])(?:\s+|$)/);
      if (sentence) { this.enqueue(sentence[1]); this.buffer = this.buffer.slice(sentence[0].length); }
      else if (this.buffer.length > 240) { const end = this.buffer.lastIndexOf(' ', 220); this.enqueue(this.buffer.slice(0, end > 0 ? end : 220)); this.buffer = this.buffer.slice(end > 0 ? end + 1 : 220); }
      else break;
    }
    if (final && this.buffer.trim()) { this.enqueue(this.buffer); this.buffer = ''; }
    void this.pump();
  }

  private enqueue(sentence: string) { const s = sentence.replace(/[`*_#]/g, '').trim(); if (s) this.queue.push(s); }

  private async ensureContext(): Promise<boolean> {
    if (typeof AudioContext === 'undefined') return false;
    if (!this.context) { try { this.context = new AudioContext(); this.graph = createVoiceGraph(this.context); } catch { return false; } }
    if (this.context.state === 'suspended') { try { await this.context.resume(); } catch { /* needs a gesture; fall back */ } }
    return this.context.state === 'running';
  }

  private async pump() {
    if (this.pumping || !this.queue.length) return;
    this.pumping = true;
    const text = this.queue.shift()!;
    const epoch = this.epoch;
    try {
    // Premium path: synthesize + play through the graph.
    if (this.premium !== false && await this.ensureContext()) {
      try {
        if (epoch !== this.epoch) return;
        this.request = new AbortController();
        const response = await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal: this.request.signal });
        if (epoch !== this.epoch) return;
        if (!response.ok) { this.premium = false; throw new Error('tts unavailable'); }
        this.premium = true;
        const bytes = await response.arrayBuffer();
        if (epoch !== this.epoch || !this.context || !this.graph) return;
        const audio = await this.context.decodeAudioData(bytes);
        if (epoch !== this.epoch) return;
        await this.playBuffer(audio, epoch);
        return;
      } catch {
        // Fall through to browser speech for this sentence.
        if (epoch !== this.epoch) return;
      }
    }
    // Fallback path.
    if (epoch !== this.epoch) return;
    await new Promise<void>(resolve => {
      this.finishFallback = resolve;
      this.fallback.feed(text, true);
      if (!this.fallback.speaking) { this.finishFallback = null; resolve(); }
    });
    } finally {
      if (epoch === this.epoch) { this.pumping = false; this.request = null; void this.pump(); }
    }
  }

  private playBuffer(audio: AudioBuffer, epoch: number) {
    return new Promise<void>(resolve => {
      if (!this.context || !this.graph) { resolve(); return; }
      const source = this.context.createBufferSource();
      source.buffer = audio; source.connect(this.graph.input);
      this.source = source; this.playing = true; this.onSpeaking(true);
      const loop = () => { if (epoch !== this.epoch) return; this.graph?.update(); voiceSignal.level = fftSignal.level; this.raf = requestAnimationFrame(loop); };
      this.raf = requestAnimationFrame(loop);
      source.onended = () => {
        source.disconnect();
        if (epoch !== this.epoch) { resolve(); return; }
        cancelAnimationFrame(this.raf); voiceSignal.level = 0; fftSignal.level = 0; fftSignal.bands.fill(0);
        this.playing = false; this.source = null;
        if (epoch === this.epoch && !this.queue.length) this.onSpeaking(false);
        resolve();
      };
      try { source.start(); } catch { source.onended = null; this.playing = false; resolve(); }
    });
  }

  stop() {
    this.epoch++; this.buffer = ''; this.queue = []; this.playing = false; this.pumping = false;
    this.request?.abort(); this.request = null;
    const finish = this.finishFallback; this.finishFallback = null; finish?.();
    if (this.raf) cancelAnimationFrame(this.raf); this.raf = 0; voiceSignal.level = 0; fftSignal.level = 0; fftSignal.bands.fill(0);
    try { this.source?.stop(); } catch { /* already stopped */ } this.source = null;
    this.fallback.stop();
    this.onSpeaking(false);
  }
}
