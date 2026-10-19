import { localRequestAllowed, readBoundedJson } from '@/ai/server';
import { aiProvider } from '@/ai/ollama';
import { zenoLink } from '@/ai/zenoBrain';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
// The owner's yes or no for an action Zeno's brain is waiting on. Same-origin only:
// approving runs a state-changing tool.
export async function POST(request: Request) {
  if (!localRequestAllowed(request, true)) return Response.json({ error: 'Only same-origin requests to this local Zeno instance are allowed.' }, { status: 403 });
  if (aiProvider() !== 'zeno') return Response.json({ error: 'Approvals are only for Zeno\'s own brain.' }, { status: 409 });
  let body: { id?: unknown; approved?: unknown };
  try { body = await readBoundedJson(request, 1000); } catch { return Response.json({ error: 'Invalid request.' }, { status: 400 }); }
  if (typeof body?.id !== 'string' || !body.id || body.id.length > 64 || typeof body.approved !== 'boolean') return Response.json({ error: 'Invalid request.' }, { status: 400 });
  if (!zenoLink().decide(body.id, body.approved)) return Response.json({ error: 'That request is no longer waiting for an answer.' }, { status: 404 });
  return Response.json({ ok: true });
}
