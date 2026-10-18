import { voiceSignal } from '@/stores/assistant';
export class SentenceSpeaker {
  private buffer = '';
  private queue: string[] = [];
  private current: SpeechSynthesisUtterance | null = null;
  private epoch = 0;
  private interval: ReturnType<typeof setInterval> | null = null;
  private pulseAt = 0;
  private startedAt = 0;
  private hadBoundary = false;
  constructor(private onSpeaking: (speaking: boolean) => void, private voiceURI: () => string, private style: () => 'ultron' | 'natural' = () => 'natural') {}
  get speaking() { return this.current !== null || this.queue.length > 0; }
  feed(text: string, final = false) {
    if (typeof speechSynthesis === 'undefined') return;
    this.buffer += text;
    for (;;) {
      const sentence = this.buffer.match(/^([\s\S]*?[.!?])(?:\s+|$)/);
      if (sentence) { this.queue.push(sentence[1]); this.buffer = this.buffer.slice(sentence[0].length); }
      else if (this.buffer.length > 240) { const end = this.buffer.lastIndexOf(' ', 220); this.queue.push(this.buffer.slice(0, end > 0 ? end : 220)); this.buffer = this.buffer.slice(end > 0 ? end + 1 : 220); }
      else break;
    }
    if (final && this.buffer.trim()) { this.queue.push(this.buffer); this.buffer = ''; }
    this.playNext();
  }
  private playNext() {
    if (this.current || !this.queue.length) return;
    const text = this.queue.shift()!.replace(/[`*_#]/g, '').trim();
    if (!text) { this.playNext(); return; }
    const u = new SpeechSynthesisUtterance(text); const epoch = this.epoch;
    const voices = speechSynthesis.getVoices();
    // Prefer a deep male neural voice (Edge's "Online (Natural)" voices sound
    // human), then any natural/neural English voice, then the default.
    const english = voices.filter(v => /^en/i.test(v.lang)), natural = english.filter(v => /natural|neural|enhanced|premium/i.test(v.name));
    const deep = /\b(guy|christopher|andrew|brian|davis|eric|roger|ryan|thomas|steffan|william|george|daniel|david|mark)\b/i;
    u.voice = voices.find(v => v.voiceURI === this.voiceURI()) ?? natural.find(v => deep.test(v.name)) ?? natural[0] ?? english.find(v => deep.test(v.name)) ?? english.find(v => v.default) ?? english[0] ?? null;
    const ultron = this.style() === 'ultron';
    u.rate = ultron ? .94 : 1.02; u.pitch = ultron ? .72 : 1; u.volume = .9;
    this.current = u; this.startedAt = performance.now(); this.hadBoundary = false;
    u.onstart = () => {
      if (epoch !== this.epoch) return;
      this.onSpeaking(true);
      this.interval = setInterval(() => {
        const now = performance.now();
        const phase = this.hadBoundary ? now - this.pulseAt : (now - this.startedAt) % 310;
        const level = phase < 80 ? phase / 80 : Math.max(0, 1 - (phase - 80) / 220);
        voiceSignal.level = Math.round(level * 4) / 4;
      }, 40);
    };
    u.onboundary = e => { if (epoch === this.epoch && e.name === 'word') { this.hadBoundary = true; this.pulseAt = performance.now(); } };
    const ended = () => {
      if (epoch !== this.epoch) return;
      if (this.interval) clearInterval(this.interval); this.interval = null; voiceSignal.level = 0; this.current = null;
      if (this.queue.length) this.playNext(); else this.onSpeaking(false);
    };
    u.onend = ended; u.onerror = ended; speechSynthesis.speak(u);
  }
  stop() {
    this.epoch++; this.buffer = ''; this.queue = []; this.current = null;
    if (this.interval) clearInterval(this.interval); this.interval = null; voiceSignal.level = 0;
    if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
    this.onSpeaking(false);
  }
}

export interface RecognitionResult { isFinal: boolean; 0: { transcript: string }; }
export interface RecognitionEvent { resultIndex: number; results: { length: number; [index: number]: RecognitionResult }; }
export interface Recognition {
  continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null; onspeechstart: (() => void) | null;
  start(): void; stop(): void; abort(): void;
}
export function recognitionConstructor(): (new () => Recognition) | undefined {
  if (typeof window === 'undefined') return undefined;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}
