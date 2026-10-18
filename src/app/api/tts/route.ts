import { localRequestAllowed, readBoundedJson } from '@/ai/server';
import { synthesize, ttsProvider, ttsStatus } from '@/ai/tts';
import { synthesizeLocal } from '@/ai/localVoice';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// GET reports whether the premium voice is configured (the client decides
// whether to use it or fall back to browser speech).
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local requests only.' }, { status: 403 });
  return Response.json(ttsStatus(), { headers: { 'Cache-Control': 'no-store' } });
}

// POST { text, speed? } -> audio for one sentence: ElevenLabs (mpeg) or the
// local neural voice (wav). 503 while the local voice is still loading.
export async function POST(request: Request) {
  if (!localRequestAllowed(request, true)) return Response.json({ error: 'Only same-origin local requests are allowed.' }, { status: 403 });
  if (ttsProvider() === 'none') return Response.json({ error: 'Premium voice is not configured.' }, { status: 503 });
  if (!request.headers.get('content-type')?.includes('application/json')) return Response.json({ error: 'JSON required.' }, { status: 415 });
  let body: unknown;
  try { body = await readBoundedJson(request, 8000); } catch { return Response.json({ error: 'Invalid request.' }, { status: 400 }); }
  const text = (body as { text?: unknown })?.text, speed = Number((body as { speed?: unknown })?.speed) || 1;
  if (typeof text !== 'string' || !text.trim() || text.length > 1200) return Response.json({ error: 'Provide 1–1200 characters of text.' }, { status: 400 });
  const abort = new AbortController();
  const cancel = () => abort.abort(); request.signal.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(cancel, 20000);
  try {
    if (ttsProvider() === 'local') {
      const wav = await synthesizeLocal(text.trim(), speed);
      return new Response(wav, { headers: { 'Content-Type': 'audio/wav', 'Cache-Control': 'no-store' } });
    }
    const upstream = await synthesize(text.trim(), abort.signal);
    return new Response(upstream.body, { headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'no-store' } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : 'Voice synthesis failed.' }, { status: ttsProvider() === 'local' ? 503 : 502 });
  } finally { clearTimeout(timer); request.signal.removeEventListener('abort', cancel); }
}
