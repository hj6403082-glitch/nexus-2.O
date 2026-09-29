import { localRequestAllowed } from '@/ai/server';
import { aiProvider, ollamaStatus } from '@/ai/ollama';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local, same-origin requests only.' }, { status: 403 });
  return Response.json(aiProvider() === 'ollama' ? await ollamaStatus() : { configured: Boolean(process.env.GEMINI_API_KEY), provider: 'gemini', message: 'Connect Gemini using a server-side API key.', model: process.env.GEMINI_MODEL || 'gemini-3.8-flash' }, { headers: { 'Cache-Control': 'no-store' } });
}
