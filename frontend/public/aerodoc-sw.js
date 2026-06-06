/*
 * AeroDoc offline service worker.
 *
 * Important: this worker deliberately does NOT cache the portal's JavaScript or
 * CSS bundles. Caching lazy route chunks caused deployed code to mix old and new
 * assets, which can leave navigation waiting for a manual browser refresh.
 */

const CACHE_PREFIX = "aerodoc-hybrid-dms-";
const CACHE_NAME = `${CACHE_PREFIX}v2`;
const PRECACHE = ["/manuals-reader.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "CLEAR_AERODOC_CACHE") {
    event.waitUntil(
      caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX)).map((key) => caches.delete(key)))),
    );
  }
});

function shouldCache(url) {
  return url.pathname.includes("/qms/documents/") || url.pathname.includes("/qms/aerodoc/");
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || networkPromise;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !shouldCache(url)) return;
  event.respondWith(staleWhileRevalidate(request));
});
