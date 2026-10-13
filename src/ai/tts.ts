// Premium text-to-speech for the voice of NEXUS (Phase 8, Objective 4).
//
// Default provider: ElevenLabs. The spec asked for a "Bold", "Brave",
// "Authoritative" voice — deep, resonant and natural — so the default voice is
// a deep, commanding model and the settings favour stability and presence. The
// key stays server-side; audio is proxied to the local client, which routes it
// through the Web Audio cinematic graph (sub-bass + spatial reverb) and the FFT
// analyser that drives the humanoid's face.
//
// When ELEVENLABS_API_KEY is not set, the route reports unavailable and the
// client falls back to the browser's built-in speech synthesis.

export const ttsProvider = () => (process.env.ELEVENLABS_API_KEY ? 'elevenlabs' : 'none');

// "Daniel" — a deep, authoritative delivery — is a sensible default; override
// with ELEVENLABS_VOICE_ID for any voice on your account.
const DEFAULT_VOICE = process.env.ELEVENLABS_VOICE_ID || 'onwK4e9ZLuTAKqWW03F9';
const DEFAULT_MODEL = process.env.ELEVENLABS_MODEL || 'eleven_turbo_v2_5';

export function ttsStatus() {
  const provider = ttsProvider();
  return {
    provider,
    configured: provider !== 'none',
    message: provider === 'elevenlabs'
      ? `Premium voice · ElevenLabs (${DEFAULT_VOICE})`
      : 'Add ELEVENLABS_API_KEY to .env.local for the premium NEXUS voice. The browser voice is used until then.',
  };
}

// Fetch synthesized speech for one sentence. Returns the upstream audio
// response (audio/mpeg) to stream straight to the client.
export async function synthesize(text: string, signal: AbortSignal): Promise<Response> {
  const key = process.env.ELEVENLABS_API_KEY;
  if (!key) throw new Error('Premium voice is not configured.');
  const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(DEFAULT_VOICE)}/stream`, {
    method: 'POST', signal,
    headers: { 'xi-api-key': key, 'Content-Type': 'application/json', Accept: 'audio/mpeg' },
    body: JSON.stringify({
      text, model_id: DEFAULT_MODEL,
      // Deep, stable, authoritative: high stability, moderate similarity, a
      // touch of style for gravitas.
      voice_settings: { stability: 0.55, similarity_boost: 0.75, style: 0.35, use_speaker_boost: true },
    }),
  });
  if (!response.ok || !response.body) {
    await response.body?.cancel();
    const status = response.status;
    throw new Error(status === 401 ? 'ElevenLabs rejected the key.' : status === 429 ? 'ElevenLabs rate limit reached.' : `ElevenLabs could not synthesize (${status}).`);
  }
  return response;
}
