// Zeno app shell service worker. Hashed build assets and the local tracking
// models are cached so the app window opens instantly; pages always try the
// live local server first. API calls (AI brain, accounts, system) are never
// cached. If the Zeno engine is not running, the window shows a reconnect
// screen instead of a browser error page.
const VERSION = 'zeno-v2';
const SHELL = `${VERSION}-shell`, ASSETS = `${VERSION}-assets`;
const PRECACHE = ['/offline.html', '/icons/icon.svg', '/icons/icon-192.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => !key.startsWith(VERSION)).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
const immutable = path => path.startsWith('/_next/static/') || path.startsWith('/models/') || path.startsWith('/mediapipe/') || path.startsWith('/icons/');
self.addEventListener('fetch', event => {
  const request = event.request; if (request.method !== 'GET') return;
  const url = new URL(request.url); if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () => (await caches.match('/offline.html')) || new Response('Zeno is offline.', { status: 503, headers: { 'Content-Type': 'text/plain' } })));
    return;
  }
  if (immutable(url.pathname)) {
    event.respondWith(caches.open(ASSETS).then(async cache => {
      const hit = await cache.match(request); if (hit) return hit;
      const response = await fetch(request);
      if (response.ok && response.status === 200) cache.put(request, response.clone()).catch(() => {});
      return response;
    }));
  }
});
