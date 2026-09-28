import { localRequestAllowed } from '@/ai/server';
export const dynamic = 'force-dynamic';
export function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local, same-origin requests only.' }, { status: 403 });
  return Response.json({ configured: Boolean(process.env.GEMINI_API_KEY), model: process.env.GEMINI_MODEL || 'gemini-3.8-flash' }, { headers: { 'Cache-Control': 'no-store' } });
}
