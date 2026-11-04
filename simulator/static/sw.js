/**
 * Service Worker - Smart Home Voice AI
 * Scope: / and /app
 * Strategy: Precache shell & error pages, network-first for navigation with fallback to /offline.html
 * Bypass: /api/*, /ws, and all non-GET requests
 */

const CACHE_NAME = 'smarthome-cache-v1';

const SHELL_ASSETS = [
  '/offline.html',
  '/404.html',
  '/500.html',
  '/qr_expired.html',
  '/403.html',
  '/static/css/style.css',
  '/static/css/mobile_app.css',
  '/static/js/app.js',
  '/static/js/mobile_app.js',
  '/favicon.ico'
];

// 1. Install Event: Precache static assets and skip waiting
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // Individual cache additions to ensure failure of one doesn't break the rest
      await Promise.all(
        SHELL_ASSETS.map((url) =>
          cache.add(url).catch((err) => {
            console.warn('[SW] Precache skipped for ' + url + ':', err);
          })
        )
      );
    })
  );
});

// 2. Activate Event: Clean up old caches and claim clients
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch Event: Intercept GET navigations, strictly bypass /api/*, /ws, and non-GET
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Strictly ignore non-GET requests (POST, PUT, DELETE, etc.)
  if (req.method !== 'GET') {
    return;
  }

  const url = new URL(req.url);

  // Strictly ignore /api/*, /ws, and chrome-extension / external requests
  if (url.pathname.startsWith('/api/') || url.pathname === '/ws') {
    return;
  }

  // Handle navigation requests (browser page visits) with Network-First
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        const cachedOffline = await cache.match('/offline.html');
        if (cachedOffline) {
          return cachedOffline;
        }
        // Fallback response if offline.html cache match is somehow missing
        return new Response(
          '<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Mất kết nối · Nhà thông minh</title></head><body><h1>Mất kết nối tới Máy chủ Nhà thông minh</h1><p>Vui lòng kiểm tra lại kết nối mạng hoặc máy chủ.</p></body></html>',
          {
            status: 200,
            headers: { 'Content-Type': 'text/html; charset=utf-8' }
          }
        );
      })
    );
    return;
  }

  // For other same-origin GET requests (CSS, JS, images, fonts): Network-first with cache fallback
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(req)
        .then((response) => {
          // If valid response, clone and update cache
          if (response && response.status === 200 && response.type === 'basic') {
            const responseToCache = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(req, responseToCache).catch(() => {});
            });
          }
          return response;
        })
        .catch(async () => {
          const cachedResponse = await caches.match(req);
          if (cachedResponse) {
            return cachedResponse;
          }
          throw new Error('[SW] Resource unavailable offline: ' + req.url);
        })
    );
  }
});
