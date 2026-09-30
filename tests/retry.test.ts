import { test } from 'node:test';
import assert from 'node:assert/strict';
import { withModelRetry } from '../src/ai/retry';
test('overloaded model retries once before streaming', async () => { let calls = 0; const value = await withModelRetry(async () => { if (++calls === 1) throw { status: 503 }; return 'ready'; }, new AbortController().signal, 0); assert.equal(value, 'ready'); assert.equal(calls, 2); });
test('credential failures and cancelled requests never retry', async () => { let calls = 0; await assert.rejects(withModelRetry(async () => { calls++; throw { status: 401 }; }, new AbortController().signal, 0)); assert.equal(calls, 1); const abort = new AbortController(); abort.abort(); calls = 0; await assert.rejects(withModelRetry(async () => { calls++; throw { status: 503 }; }, abort.signal, 0)); assert.equal(calls, 1); });
