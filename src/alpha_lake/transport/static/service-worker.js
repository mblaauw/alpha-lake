/* Lake Watch — service worker */
var CACHE = 'lake-watch-v1';
var STATIC = ['/', '/static/index.html', '/static/styles.css', '/static/app.js', '/static/manifest.webmanifest'];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return c.addAll(STATIC);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);

  /* Static files: cache-first */
  if (STATIC.indexOf(url.pathname) !== -1 || url.pathname.indexOf('/static/') === 0) {
    e.respondWith(
      caches.match(e.request).then(function (cached) { return cached || fetch(e.request).then(function (r) { var clone = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, clone); }); return r; }); })
    );
    return;
  }

  /* API calls: network-first, cache fallback with stale banner */
  if (url.pathname.indexOf('/v1/dashboard/') === 0 || url.pathname === '/v1/health') {
    e.respondWith(
      fetch(e.request).then(function (r) {
        var clone = r.clone();
        caches.open(CACHE).then(function (c) { c.put(e.request, clone); });
        return r;
      }).catch(function () {
        return caches.match(e.request).then(function (cached) {
          if (cached) {
            var headers = new Headers(cached.headers);
            headers.set('X-Lake-Watch-Stale', 'true');
            return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers: headers });
          }
          return new Response(JSON.stringify({ error: 'offline' }), { status: 503, headers: { 'Content-Type': 'application/json' } });
        });
      })
    );
    return;
  }

  /* Everything else: network */
  e.respondWith(fetch(e.request));
});
