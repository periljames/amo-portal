/* AMO Portal offline shell service worker.
 *
 * API payloads are deliberately not stored in Cache Storage. Authenticated JSON
 * is persisted by the application in a tenant/user-scoped IndexedDB database.
 * This worker only preserves the application shell and immutable static assets.
 * Controlled document responses remain network-only in this worker. Explicit
 * offline copies are owned by the reader's device-bound encrypted IndexedDB
 * store, so Cache Storage never receives authenticated PDF bytes.
 */

const VERSION = "v8";
const SHELL_CACHE = `amo-portal-shell-${VERSION}`;
const ASSET_CACHE = `amo-portal-assets-${VERSION}`;
const CACHE_PREFIXES = ["amo-portal-shell-", "amo-portal-assets-", "aerodoc-hybrid-dms-"];
const SHELL_URLS = ["/", "/portal.webmanifest"];
// Production releases contain hundreds of lazy route chunks. Fetching every
// manifest entry with one Promise.all can exhaust Chromium/socket resources and
// can compete with the login/API traffic that the live portal actually needs.
// Keep release warming bounded while preserving the same offline cache coverage.
const PRECACHE_CONCURRENCY = 4;
let qmsWarmup = null;

async function precacheQms() {
  if (qmsWarmup) return qmsWarmup;
  qmsWarmup = (async () => {
    const response = await fetch("/portal-precache.json", { cache: "no-store" });
    if (!response.ok) return;
    const manifest = await response.json();
    const urls = [...new Set(Array.isArray(manifest.qmsUrls) ? manifest.qmsUrls : [])]
      .filter((url) => typeof url === "string" && /^\/(assets|pdfjs)\/[^?#]+$/.test(url));
    const [shellCache, assetCache] = await Promise.all([caches.open(SHELL_CACHE), caches.open(ASSET_CACHE)]);
    await precacheWithBoundedConcurrency(urls, shellCache, assetCache, 2);
  })().finally(() => { qmsWarmup = null; });
  return qmsWarmup;
}

async function cacheReleaseUrl(url, shellCache, assetCache) {
  try {
    if ((url.startsWith("/assets/") || url.startsWith("/pdfjs/")) && await assetCache.match(url)) return;
    const response = await fetch(url, { cache: "reload" });
    if (!response.ok) return;
    const target = url.startsWith("/assets/") || url.startsWith("/pdfjs/")
      ? assetCache
      : shellCache;
    await target.put(url, response);
  } catch {
    // A single optional route chunk must not abort the service-worker update.
  }
}

async function precacheWithBoundedConcurrency(urls, shellCache, assetCache, concurrency = PRECACHE_CONCURRENCY) {
  let cursor = 0;
  const workerCount = Math.min(concurrency, urls.length);
  const workers = Array.from({ length: workerCount }, async () => {
    while (cursor < urls.length) {
      const index = cursor;
      cursor += 1;
      await cacheReleaseUrl(urls[index], shellCache, assetCache);
    }
  });
  await Promise.all(workers);
}

async function precacheRelease() {
  const [shellCache, assetCache] = await Promise.all([
    caches.open(SHELL_CACHE),
    caches.open(ASSET_CACHE),
  ]);
  let urls = SHELL_URLS;
  try {
    const response = await fetch("/portal-precache.json", { cache: "no-store" });
    if (response.ok) {
      const manifest = await response.json();
      if (Array.isArray(manifest.urls)) urls = [...new Set([...SHELL_URLS, ...manifest.urls])];
    }
  } catch {
    // The minimal shell still installs during a partially available rollout.
  }
  await precacheWithBoundedConcurrency(urls, shellCache, assetCache);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    precacheRelease()
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  const active = new Set([SHELL_CACHE, ASSET_CACHE]);
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
  if (event.data?.type === "PRECACHE_QMS") event.waitUntil(precacheQms().catch(() => undefined));
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
  if (event.data?.type === "PRECACHE_RELEASE") {
    event.waitUntil(precacheRelease().catch(() => undefined));
  }
  if (event.data?.type === "CLEAR_PORTAL_CACHE") {
    event.waitUntil(
      caches.keys().then((keys) => Promise.all(
        keys.filter((key) => CACHE_PREFIXES.some((prefix) => key.startsWith(prefix))).map((key) => caches.delete(key)),
      )),
    );
  }
});

self.addEventListener("sync", (event) => {
  if (event.tag !== "amo-portal-outbox") return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => clients.forEach((client) => client.postMessage({ type: "PORTAL_SYNC_REQUESTED" }))),
  );
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

function isStaticAsset(request, url) {
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/pdfjs/")) return true;
  return [
    "/vite.svg",
    "/login-illustration-placeholder.svg",
    "/portal.webmanifest",
    "/manuals-reader.webmanifest",
  ].includes(url.pathname);
}

async function networkFirstNavigation(request, preloadResponsePromise, event) {
  const cache = await caches.open(SHELL_CACHE);
  const fallback = (await cache.match(request)) || (await cache.match("/"));
  const network = (async () => {
    try {
      const preloaded = preloadResponsePromise ? await preloadResponsePromise : null;
      const response = preloaded || await fetch(request);
      if (response.ok && (response.headers.get("Content-Type") || "").includes("text/html")) await cache.put("/", response.clone());
      if (response.status >= 500 && fallback) return fallback.clone();
      return response;
    } catch { return fallback ? fallback.clone() : Response.error(); }
  })();
  if (!fallback) return network;
  // Weak connectivity must not strand an already-cached workspace on a blank
  // navigation. Keep the refresh alive after delivering the offline shell.
  event.waitUntil(network.then(() => undefined));
  let timer;
  try {
    return await Promise.race([network, new Promise((resolve) => {
      timer = setTimeout(() => resolve(fallback.clone()), 2500);
    })]);
  } finally { clearTimeout(timer); }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(ASSET_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isApiRequest(url)) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request, event.preloadResponse, event));
    return;
  }
  if (isStaticAsset(request, url)) {
    event.respondWith(cacheFirstAsset(request));
  }
});
