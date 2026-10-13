'use strict';
const dns = require('node:dns/promises');
const net = require('node:net');
const http = require('node:http');
const https = require('node:https');

// Fail closed for IPv6 (including mapped IPv4) and non-public IPv4 ranges.
function publicIPv4(address) {
  if (net.isIP(address) !== 4) return false;
  const [a, b] = address.split('.').map(Number);
  return !(a === 0 || a === 10 || a === 127 || a >= 224 ||
    (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) || (a === 192 && [0, 168].includes(b)) ||
    (a === 198 && [18, 19, 51].includes(b)) || (a === 203 && b === 0));
}
async function resolveTarget(value, lookup = dns.lookup) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      (url.port && !['80', '443'].includes(url.port))) throw new Error('Research requires a public HTTP(S) URL on a standard port.');
  const host = url.hostname.replace(/^\[|\]$/g, '');
  const addresses = net.isIP(host) ? [{ address: host, family: net.isIP(host) }] : await lookup(host, { all: true, verbatim: true });
  if (!addresses.length || addresses.some(item => !publicIPv4(item.address))) throw new Error('Research cannot access private, local, reserved or IPv6 addresses.');
  return { url, address: addresses[0].address };
}
function requestPage(url, address) {
  return new Promise((resolve, reject) => {
    // Pin the checked address at connection time; retain the hostname for TLS.
    const request = (url.protocol === 'https:' ? https : http).get(url, {
      family: 4, agent: false, headers: { Accept: 'text/html,text/plain', 'Accept-Encoding': 'identity' },
      lookup: (_host, options, callback) => options.all ? callback(null, [{ address, family: 4 }]) : callback(null, address, 4),
    }, response => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        response.resume(); resolve({ redirect: response.headers.location }); return;
      }
      if (response.statusCode < 200 || response.statusCode >= 300 || !/^text\/(html|plain)/i.test(response.headers['content-type'] || '')) {
        response.resume(); reject(new Error('Research requires a successful HTML or plain-text page.')); return;
      }
      let size = 0; const chunks = [];
      response.on('data', chunk => { size += chunk.length; if (size > 1024 * 1024) request.destroy(new Error('Research page exceeds 1 MB.')); else chunks.push(chunk); });
      response.on('end', () => resolve({ text: Buffer.concat(chunks).toString('utf8') }));
      response.on('error', reject);
    });
    const timer = setTimeout(() => request.destroy(new Error('Research request timed out.')), 10000);
    request.on('close', () => clearTimeout(timer)); request.on('error', reject);
  });
}
async function research(value, dependencies = {}) {
  let target = value;
  for (let redirects = 0; redirects <= 4; redirects++) {
    const { url, address } = await resolveTarget(target, dependencies.lookup);
    const result = await (dependencies.requestPage || requestPage)(url, address);
    if (result.redirect) { target = new URL(result.redirect, url).href; continue; }
    if (typeof result.text !== 'string') throw new Error('Research returned an invalid redirect.');
    const title = result.text.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.replace(/<[^>]*>/g, '').slice(0, 200) || url.hostname;
    const text = result.text.replace(/<(script|style|noscript)\b[^>]*>[\s\S]*?<\/\1>/gi, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 8000);
    return { url: url.href, title, text, links: [], source: 'Static page text; scripts and subresources are not loaded.' };
  }
  throw new Error('Research redirect limit exceeded.');
}
module.exports = { research, resolveTarget, publicIPv4 };
