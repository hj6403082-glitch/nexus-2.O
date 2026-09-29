import { isModule } from './protocol';
export type AIRequest = { messages: { role: 'user' | 'assistant'; text: string }[]; context: { module: string; description: string; connected: boolean } };
export function validateRequest(value: unknown): AIRequest | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  if (!Array.isArray(v.messages) || !v.messages.length || v.messages.length > 24) return null;
  let length = 0;
  const messages: AIRequest['messages'] = [];
  for (const m of v.messages) {
    if (!m || !['user', 'assistant'].includes(m.role) || typeof m.text !== 'string' || !m.text.trim() || m.text.length > 6000) return null;
    length += m.text.length; messages.push({ role: m.role, text: m.text });
  }
  if (length > 24000 || messages.at(-1)?.role !== 'user') return null;
  const c = v.context as Record<string, unknown> | undefined;
  if (!c || (!isModule(c.module) && c.module !== 'orbit') || typeof c.description !== 'string' || c.description.length > 4000) return null;
  return { messages, context: { module: String(c.module), description: c.description, connected: c.connected === true } };
}
export function localRequestAllowed(request: Request, mutation = false) {
  // Next's dev server may normalize request.url to localhost while the browser
  // uses 127.0.0.1. Validate the actual Host authority, without trusting proxies.
  const authority = request.headers.get('host');
  if (!authority) return false;
  let url: URL;
  try { url = new URL(`${new URL(request.url).protocol}//${authority}`); } catch { return false; }
  if (url.host !== authority || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) return false;
  const origin = request.headers.get('origin');
  if (mutation && !origin) return false;
  if (origin && origin !== url.origin) return false;
  const site = request.headers.get('sec-fetch-site');
  return !site || site === 'same-origin' || site === 'none';
}
export async function readBoundedJson(request: Request, maxBytes = 40000) {
  const reader = request.body?.getReader(); if (!reader) throw new Error('No request body.');
  const decoder = new TextDecoder(); let bytes = 0, text = '';
  try {
    while (true) { const { done, value } = await reader.read(); if (done) break; bytes += value.byteLength; if (bytes > maxBytes) { await reader.cancel(); throw new Error('Request too large.'); } text += decoder.decode(value, { stream: true }); }
    text += decoder.decode(); return JSON.parse(text);
  } finally { reader.releaseLock(); }
}
