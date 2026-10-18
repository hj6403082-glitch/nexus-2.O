// Protocol-compatible stand-in for Ollama, for exercising NEXUS's AI-brain
// paths (status, streaming, tool calls, model download, failures) on machines
// without a real model. It does not generate real answers.
//   node scripts/mock-ollama.mjs            # starts with no models installed
//   MOCK_MODELS=qwen3:1.7b node scripts/mock-ollama.mjs
//   MOCK_TOOLS=0 ...   # models reject tools (exercises the plain-chat retry)
import http from 'node:http';
const models = new Set((process.env.MOCK_MODELS || '').split(',').filter(Boolean));
const tools = process.env.MOCK_TOOLS !== '0';
const port = Number(process.env.MOCK_PORT || 11434);
const read = req => new Promise(resolve => { let body = ''; req.on('data', c => body += c); req.on('end', () => { try { resolve(JSON.parse(body || '{}')); } catch { resolve({}); } }); });
const wait = ms => new Promise(r => setTimeout(r, ms));
http.createServer(async (req, res) => {
  if (req.url === '/api/tags') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ models: [...models].map(name => ({ name })) })); return; }
  if (req.url === '/api/pull' && req.method === 'POST') {
    const { model } = await read(req); res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
    if (model === 'missing:model') { res.end(JSON.stringify({ error: 'pull model manifest: file does not exist' }) + '\n'); return; }
    res.write(JSON.stringify({ status: 'pulling manifest' }) + '\n');
    for (let done = 0; done <= 100; done += 20) { await wait(Number(process.env.MOCK_PULL_MS || 150)); res.write(JSON.stringify({ status: 'pulling 6f2a', digest: 'sha256:6f2a', total: 100, completed: done }) + '\n'); }
    res.write(JSON.stringify({ status: 'verifying sha256 digest' }) + '\n'); models.add(model); res.end(JSON.stringify({ status: 'success' }) + '\n'); return;
  }
  if (req.url === '/api/chat' && req.method === 'POST') {
    const body = await read(req);
    if (!models.has(body.model)) { res.writeHead(404, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: `model "${body.model}" not found, try pulling it first` })); return; }
    if (body.tools && !tools) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: `${body.model} does not support tools` })); return; }
    res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
    const last = body.messages?.at(-1)?.content || '';
    const send = message => res.write(JSON.stringify({ model: body.model, message: { role: 'assistant', content: '', ...message }, done: false }) + '\n');
    if (/become human|human form/i.test(last) && body.tools) send({ tool_calls: [{ function: { name: 'transform_form', arguments: { form: 'human' } } }] });
    const words = `<think>internal reasoning that must never be shown</think>Stand-in brain online. You said: "${last.slice(0, 80)}". Real answers need a real local model.`.match(/.{1,7}/gs);
    for (const w of words) { if (res.destroyed) return; send({ content: w }); await wait(40); }
    if (/drop the line/i.test(last)) { res.destroy(); return; }
    res.end(JSON.stringify({ model: body.model, message: { role: 'assistant', content: '' }, done: true, done_reason: 'stop' }) + '\n'); return;
  }
  res.writeHead(404); res.end();
}).listen(port, '127.0.0.1', () => console.log(`mock ollama on ${port} · models: ${[...models].join(', ') || 'none'} · tools ${tools}`));
