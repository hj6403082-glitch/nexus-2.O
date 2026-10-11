import { localRequestAllowed } from '@/ai/server';
import { aiProvider, ollamaStatus } from '@/ai/ollama';
import { grokModel } from '@/ai/grok';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local, same-origin requests only.' }, { status: 403 });
  if (aiProvider() === 'grok') return Response.json({ configured: Boolean(process.env.XAI_API_KEY), provider: 'grok', message: 'Connect Grok using a server-side xAI API key.', model: grokModel() }, { headers: { 'Cache-Control': 'no-store' } });
  return Response.json(aiProvider() === 'ollama' ? await ollamaStatus() : { configured: Boolean(process.env.GEMINI_API_KEY), provider: 'gemini', message: 'Connect Gemini using a server-side API key.', model: process.env.GEMINI_MODEL || 'gemini-3.8-flash' }, { headers: { 'Cache-Control': 'no-store' } });
}
