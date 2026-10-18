import type { AIRequest } from './server';
import { validateCommand, type StreamEvent } from './protocol';
import { systemPrompt } from './persona';
export const aiProvider = () => process.env.AI_PROVIDER === 'grok' ? 'grok' : process.env.AI_PROVIDER === 'gemini' ? 'gemini' : process.env.AI_PROVIDER === 'ollama' ? 'ollama' : process.env.XAI_API_KEY ? 'grok' : process.env.GEMINI_API_KEY ? 'gemini' : 'ollama';
// Ollama listens on this computer. OLLAMA_URL is NEXUS's own override; Ollama's
// OLLAMA_HOST is a bind address (often 0.0.0.0) and is deliberately not reused.
export const ollamaUrl = () => (process.env.OLLAMA_URL || 'http://127.0.0.1:11434').replace(/\/+$/, '');
export type OllamaState = 'offline' | 'no-model' | 'model-missing' | 'ready';
export type OllamaStatus = { configured: boolean; model: string; wanted: string; models: string[]; provider: 'ollama'; state: OllamaState; message: string };
// "qwen3" and "qwen3:latest" name the same model; tags are otherwise exact.
export function resolveModel(models: string[], wanted: string) {
  if (!wanted) return models[0] || '';
  const base = (name: string) => name.toLowerCase().replace(/:latest$/, '');
  return models.find(name => name === wanted) || models.find(name => base(name) === base(wanted)) || '';
}
export async function ollamaStatus(): Promise<OllamaStatus> {
  const wanted = (process.env.OLLAMA_MODEL || '').trim();
  let models: string[];
  try {
    const response = await fetch(`${ollamaUrl()}/api/tags`, { signal: AbortSignal.timeout(2500), cache: 'no-store' });
    if (!response.ok) throw new Error();
    const data = await response.json().catch(() => ({}));
    models = (Array.isArray(data?.models) ? data.models : []).map((m: { name?: unknown }) => m?.name).filter((name: unknown): name is string => typeof name === 'string' && !name.endsWith(':cloud') && !name.endsWith('-cloud'));
  } catch {
    return { configured: false, model: wanted, wanted, models: [], provider: 'ollama', state: 'offline', message: 'Ollama is not running on this computer. Open the Ollama app (it starts automatically after install), then check the connection. No API key is needed.' };
  }
  if (!models.length) return { configured: false, model: wanted || 'qwen3:1.7b', wanted, models, provider: 'ollama', state: 'no-model', message: 'Ollama is running but has no local model yet. Download one below; NEXUS stays usable for module commands meanwhile.' };
  const exact = resolveModel(models, wanted);
  if (exact) return { configured: true, model: exact, wanted, models, provider: 'ollama', state: 'ready', message: `Local Ollama · ${exact}` };
  // The configured model is missing but another one is installed: keep the brain
  // working on what is there rather than failing every question.
  return { configured: true, model: models[0], wanted, models, provider: 'ollama', state: 'model-missing', message: `${wanted} is not downloaded, so NEXUS is using ${models[0]}. Download ${wanted} below to switch.` };
}
// Older Ollama builds ignore `think: false`, so reasoning models can still emit
// <think>…</think>. Strip it across arbitrary chunk boundaries.
export class ThinkFilter {
  private inside = false; private carry = '';
  push(text: string) {
    let input = this.carry + text, out = ''; this.carry = '';
    while (input) {
      const tag = this.inside ? '</think>' : '<think>', at = input.indexOf(tag);
      if (at >= 0) { if (!this.inside) out += input.slice(0, at); input = input.slice(at + tag.length); this.inside = !this.inside; continue; }
      // Hold back a possible partial tag at the end of this chunk.
      let keep = 0; for (let k = Math.min(tag.length - 1, input.length); k > 0; k--) if (tag.startsWith(input.slice(-k))) { keep = k; break; }
      if (!this.inside) out += input.slice(0, input.length - keep);
      this.carry = input.slice(input.length - keep); input = '';
    }
    return out;
  }
  flush() { const rest = this.inside ? '' : this.carry; this.carry = ''; return rest; }
}
const friendlyModelError = (text: string) => /memory|cuda|out of|alloc/i.test(text) ? 'The local model ran out of memory. Close some apps or choose a smaller model with OLLAMA_MODEL.' : /not found|pull/i.test(text) ? 'That Ollama model is not downloaded. Download it from Ask NEXUS, then retry.' : 'Ollama reported a model error. Check the model and available memory, then retry.';
async function startChat(body: Record<string, unknown>, signal: AbortSignal) {
  try { return await fetch(`${ollamaUrl()}/api/chat`, { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
  catch (error) { if (signal.aborted) throw error; throw new Error('Ollama stopped responding. Make sure the Ollama app is running, then retry.'); }
}
export async function* streamOllama(input: AIRequest, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const status = await ollamaStatus();
  if (!status.configured) throw new Error(status.message);
  const base = { model: status.model, stream: true,
    messages: [{ role: 'system', content: systemPrompt(JSON.stringify(input.context), 'Only use tools when the user explicitly requests an action.') }, ...input.messages.map(m => ({ role: m.role, content: m.text }))],
    options: { num_ctx: 4096, num_predict: 1200 } };
  const tools = [{ type: 'function', function: { name: 'transform_form', description: 'Change human/spatial form on explicit request.', parameters: { type: 'object', properties: { form: { type: 'string', enum: ['human', 'spatial'] } }, required: ['form'] } } }];
  let response = await startChat({ ...base, think: false, tools }, signal);
  // Models without tool or thinking support answer 400; retry plainly so any
  // installed chat model still works (local commands still drive the UI).
  if (response.status === 400) { await response.body?.cancel().catch(() => {}); response = await startChat(base, signal); }
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => '');
    throw new Error(response.status === 404 ? 'That Ollama model is not downloaded. Download it from Ask NEXUS, then retry.' : response.status >= 500 ? friendlyModelError(detail) : 'Ollama could not start the response. Check that the selected model supports chat.');
  }
  const reader = response.body.getReader(), decoder = new TextDecoder(), think = new ThinkFilter();
  let buffer = '', done = false, commandSent = false, any = false;
  try {
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try { chunk = await reader.read(); }
      catch (error) { if (signal.aborted) throw error; throw new Error('Ollama stopped mid-answer. Make sure it is still running, then retry.'); }
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      const lines = buffer.split('\n'); buffer = lines.pop() || ''; if (chunk.done && buffer.trim()) { lines.push(buffer); buffer = ''; }
      for (const line of lines) {
        if (!line.trim()) continue;
        let item; try { item = JSON.parse(line); } catch { throw new Error('Ollama returned an unreadable response. Retry, or update Ollama.'); }
        if (item.error) throw new Error(friendlyModelError(String(item.error)));
        if (typeof item.message?.content === 'string' && item.message.content) { const text = think.push(item.message.content); if (text) { any = true; yield { type: 'text', text }; } }
        for (const call of Array.isArray(item.message?.tool_calls) ? item.message.tool_calls : []) { if (call?.function?.name === 'transform_form' && !commandSent) { const command = validateCommand({ type: 'transform', form: call.function.arguments?.form }); if (command) { yield { type: 'command', command }; commandSent = any = true; } } }
        if (item.done) done = true;
      }
      if (buffer.length > 100000) throw new Error('The local model returned an oversized response chunk.');
      if (chunk.done || done) break;
    }
    const rest = think.flush(); if (rest) { any = true; yield { type: 'text', text: rest }; }
    if (!done) throw new Error('The local model response ended early. Please retry.');
    if (!any) throw new Error('The local model returned an empty answer. Try rephrasing, or choose a different model.');
    yield { type: 'done' };
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
// Model download for people who never open a terminal: proxies Ollama's pull
// progress as {status, completed, total} lines.
export const validModelName = (value: unknown): value is string => typeof value === 'string' && /^[a-z0-9][a-z0-9._\-/]{0,80}(?::[a-z0-9._-]{1,40})?$/i.test(value);
export async function* pullOllama(model: string, signal: AbortSignal): AsyncGenerator<{ status: string; completed?: number; total?: number }> {
  let response: Response;
  try { response = await fetch(`${ollamaUrl()}/api/pull`, { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model, stream: true }) }); }
  catch (error) { if (signal.aborted) throw error; throw new Error('Ollama is not running. Open the Ollama app, then retry the download.'); }
  if (!response.ok || !response.body) throw new Error(response.status === 404 || response.status === 400 ? `Ollama could not find "${model}". Check the model name.` : 'Ollama could not start the download. Check your internet connection.');
  const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '', success = false;
  try {
    while (true) {
      const chunk = await reader.read(); buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      const lines = buffer.split('\n'); buffer = lines.pop() || ''; if (chunk.done && buffer.trim()) lines.push(buffer);
      for (const line of lines) {
        if (!line.trim()) continue;
        let item; try { item = JSON.parse(line); } catch { continue; }
        if (item.error) throw new Error(/not found|manifest/i.test(String(item.error)) ? `Ollama could not find "${model}". Check the model name.` : 'The download failed. Check your internet connection and free disk space, then retry.');
        const status = typeof item.status === 'string' ? item.status : '';
        if (status === 'success') success = true;
        yield { status, ...(Number.isFinite(item.completed) ? { completed: item.completed } : {}), ...(Number.isFinite(item.total) ? { total: item.total } : {}) };
      }
      if (chunk.done) break;
    }
    if (!success) throw new Error('The download stopped before it finished. Retry to resume it.');
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
