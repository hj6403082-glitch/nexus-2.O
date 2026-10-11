// Optional: makes one real model request using the local server's configured provider.
const base = process.env.NEXUS_TEST_URL || 'http://127.0.0.1:3001';
const response = await fetch(`${base}/api/ai`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Origin: base },
  body: JSON.stringify({ messages: [{ role: 'user', text: 'Reply with the word ready.' }], context: { module: 'orbit', description: 'Connection verification. No account data.', connected: false } }),
  signal: AbortSignal.timeout(70000),
});
if (!response.ok) { console.error(`AI request rejected: HTTP ${response.status}`); process.exitCode = 1; }
else {
  const events = (await response.text()).trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
  const failure = events.find(event => event.type === 'error');
  const characters = events.filter(event => event.type === 'text').reduce((count, event) => count + event.text.length, 0);
  if (failure || !characters || !events.some(event => event.type === 'done')) { console.error(failure?.message || 'AI stream did not complete with text.'); process.exitCode = 1; }
  else console.log(`Live AI stream passed: ${characters} response characters and a completion event.`);
}
