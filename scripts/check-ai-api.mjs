import assert from 'node:assert/strict';
const base = process.env.NEXUS_TEST_URL || 'http://127.0.0.1:3001';
const status = await fetch(`${base}/api/ai/status`);
assert.equal(status.status, 200);
const connection = await status.json();
const body = JSON.stringify({ messages: [{ role: 'user', text: 'Hello' }], context: { module: 'orbit', description: 'Spatial orbit', connected: false } });
const foreign = await fetch(`${base}/api/ai`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://example.com' }, body });
assert.equal(foreign.status, 403);
const invalid = await fetch(`${base}/api/ai`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: base }, body: '{}' });
assert.equal(invalid.status, 400);
if (!connection.configured) {
  const disconnected = await fetch(`${base}/api/ai`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: base }, body });
  assert.equal(disconnected.status, 503);
  assert.match((await disconnected.json()).error, /GEMINI_API_KEY/);
}
console.log('Passed: status endpoint, cross-origin rejection, request validation, and disconnected-state recovery. No paid model call was made.');
