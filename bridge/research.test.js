const { test } = require('node:test');
const assert = require('node:assert/strict');
const { resolveTarget, research } = require('./research');
const publicDNS = async () => [{ address: '93.184.215.14', family: 4 }];
test('research rejects private DNS, alternate loopback, IPv6 and credentials', async () => {
  for (const url of ['http://127.1', 'http://2130706433', 'http://[::1]', 'http://[::ffff:127.0.0.1]', 'http://10.0.0.1', 'http://192.168.1.1', 'http://169.254.1.2', 'http://user:pass@example.com']) await assert.rejects(resolveTarget(url, publicDNS));
  await assert.rejects(resolveTarget('https://example.com', async () => [{ address: '10.1.2.3', family: 4 }]));
});
test('research pins the checked address and refuses private redirects before connecting', async () => {
  let calls = 0;
  await assert.rejects(research('https://example.com', { lookup: publicDNS, requestPage: async (_url, address) => { calls++; assert.equal(address, '93.184.215.14'); return { redirect: 'http://127.0.0.1:4517' }; } }));
  assert.equal(calls, 1);
});
test('research never executes scripts or loads page subresources', async () => {
  let calls = 0;
  const result = await research('https://example.com', { lookup: publicDNS, requestPage: async () => { calls++; return { text: '<title>Example</title><script>secret()</script><img src="http://localhost"><p>Visible text</p>' }; } });
  assert.equal(calls, 1); assert.equal(result.title, 'Example'); assert.match(result.text, /Visible text/); assert.doesNotMatch(result.text, /secret|localhost/);
});
