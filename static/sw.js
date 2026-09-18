// Smart Water PWA service worker.
// Served at /sw.js (root scope) by core.views.service_worker_view, not
// directly from /static/ -- a service worker's control scope is limited to
// the directory it's served from, and this app needs to control the whole
// site (order pages, staff panel, etc.), not just /static/.
//
// Bump CACHE_NAME whenever STATIC_PRECACHE below changes, so old clients
// pick up the new list on next visit instead of serving a stale cache
// forever.
const CACHE_NAME = "smartwater-cache-v1";
const OFFLINE_URL = "/offline/";

const STATIC_PRECACHE = [
  OFFLINE_URL,
  "/static/css/style.css",
  "/static/img/favicon.svg",
  "/static/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Never intercept non-GET requests (form POSTs -- order creation, login,
  // delivery confirm, etc.) -- those need a real network round-trip every
  // time, and the browser's default offline error is the correct behavior
  // for "you tried to submit a form with no connection", not a cached page.
  if (request.method !== "GET") return;

  // Page navigations: network-first (so logged-in / order-status content is
  // always fresh when online), falling back to a cached copy of that exact
  // page, and finally to the offline page if neither is available.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match(OFFLINE_URL)))
    );
    return;
  }

  // Static assets (css/js/images/manifest): cache-first, since these don't
  // change per-request and this keeps the app shell loading instantly.
  if (request.url.includes("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        return response;
      }))
    );
    return;
  }

  // Everything else (API-ish GETs, etc.): just go to the network.
});
