/* AMO Portal offline shell service worker.
 *
 * API payloads are deliberately not stored in Cache Storage. Authenticated JSON
 * is persisted by the application in a tenant/user-scoped IndexedDB database.
 * This worker only preserves the application shell, immutable static assets and
 * the existing AeroDoc document-reader cache behaviour.
 */

const VERSION = "v3";
const SHELL_CACHE = `amo-portal-shell-${VERSION}`;
const ASSET_CACHE = `amo-portal-assets-${VERSION}`;
const DOCUMENT_CACHE = `aerodoc-hybrid-dms-${VERSION}`;
const CACHE_PREFIXES = ["amo-portal-shell-", "amo-portal-assets-", "aerodoc-hybrid-dms-"];
const SHELL_URLS = ["/", "/portal.webmanifest"];

function manifestAssets(manifest) {
  const assets = new Set();
  Object.values(manifest || {}).forEach((entry) => {
    if (!entry || typeof entry !== "object") return;
    if (entry.file) assets.add(`/${String(entry.file).replace(/^\//, "")}`);
    [...(entry.css || []), ...(entry.assets || [])].forEach((value) => {
      assets.add(`/${String(value).replace(/^\//, "")}`);
    });
  });
  return [...assets];
}

async function precacheApplicationShell() {
  const shellCache = await caches.open(SHELL_CACHE);
  const assetCache = await caches.open(ASSET_CACHE);
  await Promise.all(SHELL_URLS.map((url) => shellCache.add(url).catch(() => undefined)));
  for (const manifestUrl of ["/.vite/manifest.json", "/manifest.json"]) {
    try {
      const response = await fetch(manifestUrl, { cache: "no-store" });
      if (!response.ok) continue;
      const manifest = await response.json();
      const assets = manifestAssets(manifest);
      await Promise.all(assets.map((url) => assetCache.add(url).catch(() => undefined)));
      break;
    } catch {
      // Some hosts do not expose the Vite manifest. Runtime asset caching still applies.
    }
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    precacheApplicationShell()
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("sync", (event) => {
  if (event.tag !== "amo-portal-outbox") return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => clients.forEach((client) => client.postMessage({ type: "PORTAL_CONNECTIVITY_RECHECK" }))),
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
