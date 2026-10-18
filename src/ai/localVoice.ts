// Local neural voice for NEXUS: Kokoro-82M (Apache-2.0) running inside the
// NEXUS engine on this computer — a natural human voice with no account, key
// or per-use cost. The model (about 90 MB) downloads once on first use and is
// cached under .nexus-cache; voices ship with the kokoro-js package. Until it
// is ready, or if it cannot load, the client keeps speaking with the browser's
// best natural voice, so speech never stops working.
import path from 'node:path';
import type { KokoroTTS } from 'kokoro-js';

export const LOCAL_VOICE = process.env.NEXUS_VOICE_ID || 'am_michael';
export const localVoiceEnabled = () => process.env.NEXUS_LOCAL_VOICE !== 'off';
type State = { state: 'idle' | 'loading' | 'ready' | 'failed'; progress: number; error?: string; at: number };
const status: State = { state: 'idle', progress: 0, at: 0 };
let engine: Promise<KokoroTTS> | null = null;
let chain: Promise<unknown> = Promise.resolve();

export function localVoiceStatus() { return { ...status }; }

export function warmLocalVoice() {
  if (!localVoiceEnabled()) return null;
  // A failed load is retried after a minute (e.g. the first download happened offline).
  if (engine && !(status.state === 'failed' && Date.now() - status.at > 60000)) return engine;
  Object.assign(status, { state: 'loading', progress: 0, error: undefined, at: Date.now() });
  engine = (async () => {
    const [{ KokoroTTS }, transformers] = await Promise.all([import('kokoro-js'), import('@huggingface/transformers')]);
    transformers.env.cacheDir = path.join(process.cwd(), '.nexus-cache', 'models');
    const files = new Map<string, number>();
    const tts = await KokoroTTS.from_pretrained('onnx-community/Kokoro-82M-v1.0-ONNX', {
      dtype: 'q8', device: 'cpu',
      progress_callback: (p: { status?: string; file?: string; progress?: number }) => {
        if (p.file && typeof p.progress === 'number') { files.set(p.file, p.progress); status.progress = Math.round([...files.values()].reduce((a, b) => a + b, 0) / files.size); }
      },
    });
    Object.assign(status, { state: 'ready', progress: 100, at: Date.now() });
    return tts;
  })();
  engine.catch(error => Object.assign(status, { state: 'failed', error: error instanceof Error ? error.message : String(error), at: Date.now() }));
  return engine;
}

// One sentence to 24 kHz WAV. Calls are serialised: the CPU model is fastest
// one utterance at a time, and order is preserved for the speaking queue.
export function synthesizeLocal(text: string, speed = 1): Promise<ArrayBuffer> {
  const ready = warmLocalVoice();
  if (!ready || status.state !== 'ready') return Promise.reject(new Error(status.state === 'failed' ? 'The local voice could not load.' : 'The local voice is still loading.'));
  const job = chain.then(async () => {
    const tts = await ready;
    const audio = await tts.generate(text, { voice: LOCAL_VOICE as Parameters<KokoroTTS['generate']>[1] extends { voice?: infer V } ? V : never, speed: Math.min(1.4, Math.max(.7, speed)) });
    return audio.toWav();
  });
  chain = job.catch(() => {});
  return job;
}
