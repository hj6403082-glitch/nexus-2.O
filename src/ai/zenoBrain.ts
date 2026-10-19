import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { AIRequest } from './server';
import { validateApproval, validateCommand, type StreamEvent } from './protocol';

// Zeno's own Python brain (brain/, `python -m zeno`). It keeps the conversation,
// memory and tools itself, so the web app sends only the newest message plus
// what is on screen, over one long-lived chat socket.

export interface ZenoSocket {
  addEventListener(type: 'message' | 'close' | 'error', listener: (event: { data?: unknown; code?: number }) => void): void;
  send(data: string): void;
  close(code?: number): void;
}
export type ZenoConnect = (url: string, headers: Record<string, string>) => ZenoSocket;
type Frame = Record<string, unknown>;
type Inbox = { id: string; frames: Frame[]; wake: (() => void) | null; closed: boolean };

const NOT_RUNNING = 'Zeno\'s brain is not running. In the brain folder, run `python -m zeno`, then retry.';
const NO_TOKEN = 'Zeno cannot find the brain\'s token yet. Start the brain once with `python -m zeno` (it creates brain/data/api-token), then retry.';
const BAD_URL = 'ZENO_BRAIN_URL must be an http address on this computer (127.0.0.1 or localhost).';
const STOPPED = 'Zeno\'s brain stopped mid-answer. Check that `python -m zeno` is still running, then retry.';
const BUSY = 'Zeno is still working on your last message.';
const STARTING = 'Zeno\'s brain is still starting (loading memory and the model). Try again in a moment.';
const REFUSED = 'Zeno\'s brain refused the connection token. Restart Zeno so it reads the brain\'s current token (brain/data/api-token).';

// The brain only listens on this computer in v1; never send the token elsewhere.
export function zenoUrl(): string | null {
  let url: URL;
  try { url = new URL(process.env.ZENO_BRAIN_URL || 'http://127.0.0.1:8765'); } catch { return null; }
  if (url.protocol !== 'http:' || url.username || url.password || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) return null;
  return url.origin;
}
export function zenoToken(): string | null {
  const fromEnv = process.env.ZENO_API_TOKEN?.trim();
  if (fromEnv) return fromEnv;
  try { return readFileSync(process.env.ZENO_API_TOKEN_FILE || join(process.cwd(), 'brain', 'data', 'api-token'), 'utf8').trim() || null; } catch { return null; }
}
// Node's built-in WebSocket takes headers and sends no Origin, which is what the
// brain expects from a local, non-browser client.
const nodeConnect: ZenoConnect = (url, headers) => new WebSocket(url, { headers } as unknown as string[]) as unknown as ZenoSocket;
function parse(data: unknown): Frame | null {
  try { const value = JSON.parse(String(data)); return value && typeof value === 'object' && typeof value.type === 'string' ? value : null; } catch { return null; }
}

export class ZenoLink {
  private socket: ZenoSocket | null = null;
  private opening: Promise<ZenoSocket> | null = null;
  private inbox: Inbox | null = null;
  private pending = new Set<string>();
  private readonly url: () => string | null;
  private readonly token: () => string | null;
  private readonly dial: ZenoConnect;
  private readonly connectTimeout: number;
  private readonly fetch: typeof fetch;
  constructor(options: { url?: string; token?: () => string | null; connect?: ZenoConnect; connectTimeout?: number; fetch?: typeof fetch } = {}) {
    this.url = options.url ? () => options.url! : zenoUrl;
    this.token = options.token ?? zenoToken;
    this.dial = options.connect ?? nodeConnect;
    this.connectTimeout = options.connectTimeout ?? 5000;
    this.fetch = options.fetch ?? ((...args) => fetch(...args));
  }

  async *turn(input: AIRequest, signal: AbortSignal): AsyncGenerator<StreamEvent> {
    // Error frames carry no turn id, so two turns on one socket could not tell
    // them apart; the brain runs one turn at a time anyway.
    if (this.inbox) throw new Error(BUSY);
    const inbox: Inbox = { id: `w${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`, frames: [], wake: null, closed: false };
    this.inbox = inbox;
    const wake = () => { const resume = inbox.wake; inbox.wake = null; resume?.(); };
    signal.addEventListener('abort', wake);
    let finished = false;
    try {
      const socket = await this.connect();
      if (signal.aborted) { finished = true; return; }
      const text = input.messages.at(-1)?.text.slice(0, 4000) ?? '';
      socket.send(JSON.stringify({ type: 'chat', id: inbox.id, text, context: JSON.stringify(input.context).slice(0, 8000) }));
      while (true) {
        if (signal.aborted) { await this.cancel(inbox); finished = true; return; }
        const frame = inbox.frames.shift();
        if (!frame) {
          if (inbox.closed) throw new Error(STOPPED);
          await new Promise<void>(resolve => { inbox.wake = resolve; });
          continue;
        }
        if (frame.type === 'error') throw new Error(typeof frame.message === 'string' && frame.message ? frame.message.slice(0, 300) : 'Zeno\'s brain could not answer. Please retry.');
        if (frame.type === 'done') { finished = true; yield { type: 'done' }; return; }
        if (frame.type === 'text' && typeof frame.text === 'string' && frame.text) yield { type: 'text', text: frame.text };
        if (frame.type === 'command') { const command = validateCommand(frame.command); if (command) yield { type: 'command', command }; }
        if (frame.type === 'approval_required') {
          const approval = validateApproval({ id: frame.request_id, tool: frame.tool, description: frame.description, args: frame.args, timeout: frame.timeout });
          if (approval) { this.pending.add(approval.id); yield { type: 'approval', approval }; }
        }
        if (frame.type === 'approval' && typeof frame.request_id === 'string' && typeof frame.approved === 'boolean') {
          this.pending.delete(frame.request_id);
          yield { type: 'decided', id: frame.request_id, approved: frame.approved };
        }
        // thought, tool_call, observation and step_rejected stay in the brain's audit log.
      }
    } finally {
      signal.removeEventListener('abort', wake);
      if (!finished && !inbox.closed && this.socket) await this.cancel(inbox); // the reader stopped early
      if (this.inbox === inbox) this.inbox = null;
      this.pending.clear();
    }
  }

  /** Answers a pending approval on the connection that received it. */
  decide(id: string, approved: boolean): boolean {
    if (!this.pending.has(id) || !this.socket) return false;
    this.pending.delete(id);
    this.socket.send(JSON.stringify({ type: 'approval', request_id: id, approved, reason: approved ? '' : 'Denied in Zeno.' }));
    return true;
  }

  // Stop the brain's turn and wait (briefly) for it to end, so the next message
  // does not find the brain still busy.
  private async cancel(inbox: Inbox) {
    if (!this.socket || inbox.closed) return;
    this.socket.send(JSON.stringify({ type: 'cancel', id: inbox.id }));
    const deadline = Date.now() + 3000;
    while (Date.now() < deadline && !inbox.closed) {
      if (inbox.frames.some(f => f.type === 'done')) return;
      await new Promise<void>(resolve => { inbox.wake = resolve; setTimeout(resolve, 100); });
    }
  }

  private async explainRefusal(url: string): Promise<Error> {
    try {
      const response = await this.fetch(`${url}/v1/status`, { signal: AbortSignal.timeout(2500), cache: 'no-store' });
      const data = await response.json();
      return new Error(data?.state === 'starting' ? STARTING : data?.state === 'ready' ? REFUSED : NOT_RUNNING);
    } catch { return new Error(NOT_RUNNING); }
  }

  private deliver(frame: Frame) {
    const inbox = this.inbox;
    if (!inbox || (frame.turn !== inbox.id && !(frame.type === 'error' && frame.turn === undefined))) return;
    inbox.frames.push(frame);
    const resume = inbox.wake; inbox.wake = null; resume?.();
  }

  private connect(): Promise<ZenoSocket> {
    if (this.socket) return Promise.resolve(this.socket);
    return this.opening ??= new Promise<ZenoSocket>((resolve, reject) => {
      const token = this.token(), url = this.url();
      if (!url) { this.opening = null; reject(new Error(BAD_URL)); return; }
      if (!token) { this.opening = null; reject(new Error(NO_TOKEN)); return; }
      let ready = false, settled = false;
      const fail = (error: Error | Promise<Error>) => {
        clearTimeout(timer); if (ready || settled) return; settled = true;
        void Promise.resolve(error).then(reason => { this.opening = null; reject(reason); });
      };
      let socket: ZenoSocket;
      try { socket = this.dial(`${url.replace(/^http/, 'ws')}/v1/chat/ws`, { Authorization: `Bearer ${token}` }); }
      catch { this.opening = null; reject(new Error(NOT_RUNNING)); return; }
      const timer = setTimeout(() => { fail(new Error('Zeno\'s brain is not responding. Restart `python -m zeno`, then retry.')); try { socket.close(); } catch { /* already closed */ } }, this.connectTimeout);
      socket.addEventListener('message', event => {
        const frame = parse(event.data); if (!frame) return;
        if (ready) { this.deliver(frame); return; }
        if (frame.type !== 'ready') return;
        ready = true; clearTimeout(timer); this.socket = socket; this.opening = null; resolve(socket);
      });
      // A refused handshake reaches a WebSocket client as a bare error (HTTP 403,
      // no close code), so the brain's status says why. Once open, an error or a
      // close both mean the connection is gone.
      const lost = () => {
        if (!ready) { fail(this.explainRefusal(url)); return; }
        if (this.socket === socket) this.socket = null;
        this.pending.clear();
        const inbox = this.inbox;
        if (inbox) { inbox.closed = true; const resume = inbox.wake; inbox.wake = null; resume?.(); }
      };
      socket.addEventListener('close', lost);
      socket.addEventListener('error', lost);
    });
  }
}

const shared = globalThis as typeof globalThis & { zenoLink?: ZenoLink };
// One link per server process (and per dev-server reload), so approvals reach the
// connection that is waiting for them.
export const zenoLink = () => shared.zenoLink ??= new ZenoLink();
export const streamZeno = (input: AIRequest, signal: AbortSignal) => zenoLink().turn(input, signal);

export type ZenoState = 'offline' | 'starting' | 'failed' | 'ready';
export type ZenoStatus = { configured: boolean; provider: 'zeno'; state: ZenoState; model: string; message: string };
export async function zenoStatus(options: { fetch?: typeof fetch; token?: () => string | null } = {}): Promise<ZenoStatus> {
  const get = options.fetch ?? fetch, token = options.token ?? zenoToken, url = zenoUrl();
  const status = (state: ZenoState, message: string, model = ''): ZenoStatus => ({ configured: state === 'ready', provider: 'zeno', state, model, message });
  if (!url) return status('offline', BAD_URL);
  let data: Record<string, unknown>;
  try {
    const response = await get(`${url}/v1/status`, { signal: AbortSignal.timeout(2500), cache: 'no-store' });
    if (!response.ok) throw new Error();
    data = await response.json();
  } catch { return status('offline', NOT_RUNNING); }
  const model = typeof data?.model === 'string' ? data.model : '';
  if (data?.state === 'starting') return status('starting', 'Zeno\'s brain is starting (loading memory and the model). This page checks again on its own.', model);
  if (data?.state === 'failed') return status('failed', `Zeno's brain could not start: ${typeof data.message === 'string' && data.message ? data.message.slice(0, 300) : 'see the brain\'s console'}. Fix it, then restart \`python -m zeno\`.`, model);
  if (data?.state !== 'ready') return status('offline', NOT_RUNNING, model);
  if (!token()) return { ...status('offline', NO_TOKEN, model) };
  return status('ready', `Zeno brain · ${model}`, model);
}
