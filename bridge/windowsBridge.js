'use strict';
// NEXUS Windows local bridge (`windowsBridge.js`).
//
// A hardened loopback daemon that lets the NEXUS web app act as an autonomous
// Windows OS agent on THIS machine only. It exposes a small HTTP surface on
// 127.0.0.1 and routes every privileged action through ./safety.js, which
// enforces an immutable destructive-command blacklist and builds explicit
// argument arrays (execFile, never a shell string).
//
// Design constraints (hard requirements, not options):
//   * Binds to 127.0.0.1 only. It never listens on 0.0.0.0 or a LAN address,
//     so nothing off this machine can reach it.
//   * Rejects cross-origin requests and non-local Host headers (anti-DNS-
//     rebinding) and requires a per-session bearer token printed at startup.
//   * Executes only named verbs from the allowlist. There is no "run this
//     command" endpoint. Arguments are validated and passed as arrays.
//   * The agentic task loop can only chain allowlisted verbs, with a step cap.
//
// Run on Windows:  node bridge/windowsBridge.js
// Optional headless research needs Playwright:  npm i playwright  (in bridge/)

const http = require('node:http');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');
const safety = require('./safety');

const HOST = '127.0.0.1';
const PORT = Number(process.env.NEXUS_BRIDGE_PORT) || 4517;
// A fresh capability token each launch. The web app must echo it as
// `Authorization: Bearer <token>`. Printed once to the console; never logged
// to disk, never sent anywhere.
const TOKEN = process.env.NEXUS_BRIDGE_TOKEN || crypto.randomBytes(24).toString('base64url');
// The single web origin allowed to drive the bridge (the local NEXUS app).
const ALLOWED_ORIGINS = new Set([
  'http://127.0.0.1:3000', 'http://localhost:3000',
  'http://127.0.0.1:3001', 'http://localhost:3001',
  ...(process.env.NEXUS_BRIDGE_ORIGIN ? [process.env.NEXUS_BRIDGE_ORIGIN] : []),
]);
const MAX_BODY = 64 * 1024;

function timingSafeEqual(a, b) {
  const x = Buffer.from(String(a)); const y = Buffer.from(String(b));
  if (x.length !== y.length) return false;
  return crypto.timingSafeEqual(x, y);
}

// Anti-DNS-rebinding: the Host authority must itself be loopback.
function hostIsLocal(req) {
  const host = req.headers.host || '';
  const name = host.replace(/:\d+$/, '').toLowerCase();
  return ['127.0.0.1', 'localhost', '[::1]', '::1'].includes(name);
}

function authorize(req) {
  if (!hostIsLocal(req)) return 'Non-local Host header rejected.';
  const origin = req.headers.origin;
  if (origin && !ALLOWED_ORIGINS.has(origin)) return 'Origin not allowed.';
  const site = req.headers['sec-fetch-site'];
  if (site && !['same-origin', 'same-site', 'none'].includes(site)) return 'Cross-site request rejected.';
  const auth = req.headers.authorization || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  if (!token || !timingSafeEqual(token, TOKEN)) return 'Missing or invalid bridge token.';
  return null;
}

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Vary': 'Origin',
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on('data', chunk => {
      size += chunk.length;
      if (size > MAX_BODY) { reject(new Error('Request body too large.')); req.destroy(); return; }
      chunks.push(chunk);
    });
    req.on('end', () => {
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { reject(new Error('Invalid JSON body.')); }
    });
    req.on('error', reject);
  });
}

// Run one allowlisted verb. Everything about the child process is decided by
// safety.planCommand — this function never sees a raw command line.
function runVerb(verb, params) {
  return new Promise((resolve, reject) => {
    let plan;
    try { plan = safety.planCommand(verb, params); }
    catch (err) { reject(err); return; }
    execFile(plan.command, plan.args, {
      timeout: plan.timeout, windowsHide: true, shell: false,
      env: { ...process.env, ...plan.env },
      maxBuffer: 4 * 1024 * 1024, cwd: process.env.SystemRoot || undefined,
    }, (error, stdout, stderr) => {
      if (error && error.killed) { reject(new Error(`Verb "${verb}" timed out.`)); return; }
      if (error) { reject(new Error(`Verb "${verb}" failed: ${String(stderr || error.message).slice(0, 400)}`)); return; }
      const text = String(stdout || '').trim();
      let data = text;
      if (text.startsWith('{') || text.startsWith('[')) { try { data = JSON.parse(text); } catch { /* keep raw text */ } }
      resolve({ verb, data, stderr: String(stderr || '').slice(0, 400) || undefined });
    });
  });
}

// Static research pins public DNS addresses and validates every redirect.
async function runResearch(params) {
  const url = safety.assertResearchUrlAllowed(params && params.url);
  return { ...await require('./research').research(url), question: String(params?.question || '').slice(0, 400) };
}

// The autonomous agentic task loop. A task is a short, server-validated list of
// steps, each naming an allowlisted verb (or `research`). Steps run in order
// with a hard cap; one failing step stops the loop and reports what completed.
// Because every step is an allowlisted verb, the loop can never run anything
// the single-verb route could not.
async function runTaskLoop(params) {
  const steps = Array.isArray(params && params.steps) ? params.steps : [];
  if (!steps.length) throw new Error('A task needs at least one step.');
  if (steps.length > 12) throw new Error('A task may contain at most 12 steps.');
  const results = [];
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i] || {};
    const verb = String(step.verb || '');
    try {
      const result = verb === 'research' ? { verb, data: await runResearch(step.params) } : await runVerb(verb, step.params);
      results.push({ step: i, verb, ok: true, ...result });
    } catch (err) {
      results.push({ step: i, verb, ok: false, error: err.message, safety: !!err.safety });
      return { completed: false, stoppedAt: i, results };
    }
  }
  return { completed: true, results };
}

const ROUTES = {
  'GET /health': () => ({ ok: true, name: 'nexus-windows-bridge', version: '1.0.0', verbs: safety.listVerbs() }),
  'POST /screen-context': () => runVerb('screen-context', {}),
  'POST /diagnostics': () => runVerb('diagnostics', {}),
  'POST /app/launch': body => runVerb('app.launch', body),
  'POST /app/window': body => runVerb('app.window', body),
  'POST /research': body => runResearch(body),
  'POST /task': body => runTaskLoop(body),
};

const server = http.createServer(async (req, res) => {
  // Browser preflight for the one allowed origin.
  if (req.method === 'OPTIONS') {
    const origin = req.headers.origin;
    const allow = origin && ALLOWED_ORIGINS.has(origin) ? origin : 'null';
    res.writeHead(204, {
      'Access-Control-Allow-Origin': allow,
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization,Content-Type',
      'Access-Control-Max-Age': '600', 'Vary': 'Origin',
    });
    res.end(); return;
  }
  const origin = req.headers.origin;
  if (origin && ALLOWED_ORIGINS.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  const key = `${req.method} ${(req.url || '').split('?')[0]}`;
  const handler = ROUTES[key];
  if (!handler) { send(res, 404, { error: 'No such endpoint.' }); return; }
  // /health is still local-only but needs no token, so the app can probe it.
  if (key !== 'GET /health') {
    const denied = authorize(req);
    if (denied) { send(res, 403, { error: denied }); return; }
  } else if (!hostIsLocal(req)) { send(res, 403, { error: 'Non-local Host header rejected.' }); return; }
  try {
    const body = req.method === 'POST' ? await readBody(req) : {};
    const result = await handler(body);
    send(res, 200, result);
  } catch (err) {
    send(res, err && err.safety ? 422 : 400, { error: err.message || 'Request failed.', safety: !!(err && err.safety) });
  }
});

// Never bind to anything but loopback.
server.listen(PORT, HOST, () => {
  // eslint-disable-next-line no-console
  console.log([
    '',
    '  NEXUS Windows bridge is running.',
    `  URL:   http://${HOST}:${PORT}`,
    `  Token: ${TOKEN}`,
    '',
    '  Paste the token into NEXUS → System → "Connect this PC".',
    '  The bridge only accepts loopback requests from the NEXUS app.',
    '',
  ].join('\n'));
});

module.exports = { server, authorize, runTaskLoop, runVerb, runResearch, TOKEN, PORT, HOST };
