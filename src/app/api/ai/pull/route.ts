import { localRequestAllowed, readBoundedJson } from '@/ai/server';
import { aiProvider, pullOllama, validModelName } from '@/ai/ollama';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
let pulling = false;
// Downloads a local Ollama model with streamed progress, so the AI brain can be
// set up from inside Zeno without a terminal.
export async function POST(request: Request) {
  if (!localRequestAllowed(request, true)) return Response.json({ error: 'Only same-origin requests to this local Zeno instance are allowed.' }, { status: 403 });
  if (aiProvider() !== 'ollama') return Response.json({ error: 'Model downloads are only for the local Ollama provider.' }, { status: 409 });
  let body: { model?: unknown };
  try { body = await readBoundedJson(request, 2000); } catch { return Response.json({ error: 'Invalid request.' }, { status: 400 }); }
  if (!validModelName(body?.model)) return Response.json({ error: 'Invalid model name.' }, { status: 400 });
  if (pulling) return Response.json({ error: 'A model download is already running.' }, { status: 429 });
  pulling = true;
  const model = body.model, abort = new AbortController(), encoder = new TextEncoder();
  const cancel = () => abort.abort(); request.signal.addEventListener('abort', cancel, { once: true });
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (value: unknown) => { try { controller.enqueue(encoder.encode(JSON.stringify(value) + '\n')); } catch { /* Reader closed. */ } };
      try { for await (const progress of pullOllama(model, abort.signal)) send({ type: 'progress', ...progress }); send({ type: 'done' }); }
      catch (error) { if (!abort.signal.aborted) send({ type: 'error', message: error instanceof Error ? error.message : 'The download failed.' }); }
      finally { pulling = false; request.signal.removeEventListener('abort', cancel); try { controller.close(); } catch { /* Reader cancelled. */ } }
    },
    cancel() { abort.abort(); },
  });
  return new Response(stream, { headers: { 'Content-Type': 'application/x-ndjson; charset=utf-8', 'Cache-Control': 'no-store, no-transform', 'X-Content-Type-Options': 'nosniff' } });
}
