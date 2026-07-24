/* AMO Portal offline shell service worker.
 *
 * API payloads are deliberately not stored in Cache Storage. Authenticated JSON
 * is persisted by the application in a tenant/user-scoped IndexedDB database.
 * This worker only preserves the application shell, immutable static assets and
 * the existing AeroDoc document-reader cache behaviour.
 */

const VERSION = "v2";
const SHELL_CACHE = `amo-portal-shell-${VERSION}`;
const ASSET_CACHE = `amo-portal-assets-${VERSION}`;
const DOCUMENT_CACHE = `aerodoc-hybrid-dms-${VERSION}`;
const CACHE_PREFIXES = ["amo-portal-shell-", "amo-portal-assets-", "aerodoc-hybrid-dms-"];
const SHELL_URLS = ["/", "/portal.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  const active = new Set([SHELL_CACHE, ASSET_CACHE, DOCUMENT_CACHE]);
  event.waitUntil(
    Promise.all([
      caches.keys()
        .then((keys) => Promise.all(
          keys
            .filter((key) => CACHE_PREFIXES.some((prefix) => key.startsWith(prefix)) && !active.has(key))
            .map((key) => caches.delete(key)),
        )),
      self.registration.navigationPreload
        ? self.registration.navigationPreload.enable()
        : Promise.resolve(),
    ]).then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "CLEAR_PORTAL_CACHE") {
    event.waitUntil(
      caches.keys().then((keys) => Promise.all(
        keys.filter((key) => CACHE_PREFIXES.some((prefix) => key.startsWith(prefix))).map((key) => caches.delete(key)),
      )),
    );
  }
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/")
    || url.pathname.startsWith("/auth/")
    || url.pathname.startsWith("/accounts/")
    || url.pathname.startsWith("/rostering/")
    || url.pathname.startsWith("/workforce/")
    || url.pathname.startsWith("/qms/")
    || url.pathname.startsWith("/training/")
    || url.pathname.startsWith("/fleet/")
    || url.pathname.startsWith("/work/");
}

function isAeroDocRequest(url) {
  return url.pathname.includes("/qms/documents/") || url.pathname.includes("/qms/aerodoc/");
}

function isStaticAsset(request, url) {
  if (request.destination && ["script", "style", "font", "image", "worker"].includes(request.destination)) return true;
  return /\.(?:js|css|woff2?|ttf|png|jpe?g|svg|webp|ico)$/i.test(url.pathname);
}

async function networkFirstNavigation(request, preloadResponsePromise) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const preloaded = preloadResponsePromise ? await preloadResponsePromise : null;
    const response = preloaded || await fetch(request);
    if (response.ok) await cache.put("/", response.clone());
    return response;
  } catch {
    return (await cache.match(request)) || (await cache.match("/")) || Response.error();
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(ASSET_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(DOCUMENT_CACHE);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response.ok) void cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || network;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isApiRequest(url) && !isAeroDocRequest(url)) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request, event.preloadResponse));
    return;
  }
  if (isAeroDocRequest(url)) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }
  if (isStaticAsset(request, url)) {
    event.respondWith(cacheFirstAsset(request));
  }
});
