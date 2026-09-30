import { setTimeout as delay } from 'node:timers/promises';
// Retry only before a stream exists; partial text and tool actions are never replayed.
export async function withModelRetry<T>(start: () => Promise<T>, signal: AbortSignal, waitMs = 1200): Promise<T> {
  try { return await start(); }
  catch (error) {
    if (signal.aborted || Number((error as { status?: number })?.status) !== 503) throw error;
    await delay(waitMs, undefined, { signal });
    return start();
  }
}
