/* AMO Portal offline shell service worker.
 *
 * API payloads are deliberately not stored in Cache Storage. Authenticated JSON
 * is persisted by the application in a tenant/user-scoped IndexedDB database.
 * This worker only preserves the application shell and immutable static assets.
 * Controlled document responses remain network-only in this worker. Explicit
 * offline copies are owned by the reader's device-bound encrypted IndexedDB
 * store, so Cache Storage never receives authenticated PDF bytes.
 */

const VERSION = "v16";
const SHELL_CACHE = `amo-portal-shell-${VERSION}`;
const ASSET_CACHE = `amo-portal-assets-${VERSION}`;
const CACHE_PREFIXES = ["amo-portal-shell-", "amo-portal-assets-", "aerodoc-hybrid-dms-"];
const SHELL_URLS = ["/", "/portal.webmanifest", "/login-illustration-placeholder.svg", "/portal-icon.svg"];
// Production releases contain hundreds of lazy route chunks. Fetching every
// manifest entry with one Promise.all can exhaust Chromium/socket resources and
// can compete with the login/API traffic that the live portal actually needs.
// Keep release warming bounded while preserving the same offline cache coverage.
const PRECACHE_CONCURRENCY = 4;
let qmsWarmup = null;
let portalWarmup = null;
let staticShellWarmup = null;

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

async function precachePortal() {
  if (portalWarmup) return portalWarmup;
  portalWarmup = (async () => {
    const response = await fetch("/portal-precache.json", { cache: "no-store" });
    if (!response.ok) return;
    const manifest = await response.json();
    const urls = [...new Set(Array.isArray(manifest.portalUrls) ? manifest.portalUrls : [])]
      .filter((url) => typeof url === "string" && /^\/(assets|pdfjs)\/[^?#]+$/.test(url));
    const [shellCache, assetCache] = await Promise.all([caches.open(SHELL_CACHE), caches.open(ASSET_CACHE)]);
    await precacheWithBoundedConcurrency(urls, shellCache, assetCache, 2);
  })().finally(() => { portalWarmup = null; });
  return portalWarmup;
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
  event.waitUntil(
    Promise.all([
      caches.keys()
        .then((keys) => {
          // Retain the previous hashed asset set for an already-open auditor
          // tab after a deployment. It may still request lazy route chunks
          // from the old release. Do not retain authenticated API data.
          const priorAssets = keys.filter((key) => key.startsWith("amo-portal-assets-") && key !== ASSET_CACHE).sort().reverse().slice(0, 1);
          const active = new Set([SHELL_CACHE, ASSET_CACHE, ...priorAssets]);
          return Promise.all(
            keys
              .filter((key) => CACHE_PREFIXES.some((prefix) => key.startsWith(prefix)) && !active.has(key))
              .map((key) => caches.delete(key)),
          );
        }),
      self.registration.navigationPreload
        ? self.registration.navigationPreload.enable()
        : Promise.resolve(),
    ]).then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "REFRESH_PORTAL_SHELL") {
    event.waitUntil((async () => {
      try {
        const response = await fetch("/", { cache: "no-store" });
        if (!response.ok || !response.headers.get("content-type")?.includes("text/html")) throw new Error("Shell unavailable");
        const cache = await caches.open(SHELL_CACHE);
        await cache.put("/", response);
        event.ports?.[0]?.postMessage({ ok: true });
      } catch { event.ports?.[0]?.postMessage({ ok: false }); }
    })());
    return;
  }
  if (event.data?.type === "PRECACHE_PORTAL") event.waitUntil(precachePortal().catch(() => undefined));
  if (event.data?.type === "PRECACHE_QMS") event.waitUntil(precacheQms().catch(() => undefined));
  if (event.data?.type === "PREPARE_AUDIT_SHELL") {
    const port = event.ports?.[0];
    event.waitUntil((async () => {
      try {
        await precacheRelease();
        await precacheQms();
        const manifestResponse = await fetch("/portal-precache.json", { cache: "no-store" });
        if (!manifestResponse.ok) throw new Error("The offline application manifest was not available.");
        const manifest = await manifestResponse.json();
        const required = [...new Set(Array.isArray(manifest.qmsUrls) ? manifest.qmsUrls : [])]
          .filter((url) => typeof url === "string" && /^\/(assets|pdfjs)\/[^?#]+$/.test(url));
        if (!required.length) throw new Error("No QMS application files were declared for offline use.");
        const assetCache = await caches.open(ASSET_CACHE);
        const shellCache = await caches.open(SHELL_CACHE);
        if (!await shellCache.match("/")) throw new Error("The offline page shell is not cached.");
        const missing = [];
        for (const url of required) {
          if (!await assetCache.match(url)) missing.push(url);
        }
        if (missing.length) throw new Error(`${missing.length} application file(s) are not available offline; reconnect and retry.`);
        port?.postMessage({ ok: true, assets: required.length });
      } catch (error) {
        port?.postMessage({ ok: false, reason: error instanceof Error ? error.message : "Offline application files could not be verified." });
      }
    })());
  }
  if (event.data?.type === "PRECACHE_STATIC_SHELL") event.waitUntil(precacheStaticShell().catch(() => undefined));
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
  if (/\.(?:svg|png|jpe?g|webp|gif|ico|woff2?)$/i.test(url.pathname)) return true;
  return [
    "/portal-icon.svg",
    "/login-illustration-placeholder.svg",
    "/portal.webmanifest",
    "/manuals-reader.webmanifest",
  ].includes(url.pathname);
}

async function matchShell(cache, request) {
  // Every SPA destination uses the same HTML. A route-specific warmup entry
  // may predate a release that already refreshed the canonical root shell.
  return (await cache.match("/")) || (await cache.match(request));
}

async function cachedShellNavigation(request, preloadResponsePromise, event) {
  const cache = await caches.open(SHELL_CACHE);
  const fallback = await matchShell(cache, request);
  const network = (async () => {
    try {
      const preloaded = preloadResponsePromise ? await preloadResponsePromise : null;
      const response = preloaded || await fetch(request);
      if (response.ok && (response.headers.get("Content-Type") || "").includes("text/html")) {
        await cache.put("/", response.clone());
      }
      // Re-match from cache instead of cloning the already-returned fallback —
      // the caller may have already consumed that Response body.
      if (response.status >= 500) {
        const cached = await matchShell(cache, request);
        if (cached) return cached;
      }
      return response;
    } catch {
      return (await matchShell(cache, request)) || Response.error();
    }
  })();
  if (!fallback) return network;
  // Prefer a healthy server's current HTML so a prior release cannot keep
  // booting removed chunks. Fall back promptly on slow/disconnected networks.
  event.waitUntil(network.then(() => undefined, () => undefined));
  let deadline;
  try {
    return await Promise.race([
      network,
      new Promise(resolve => { deadline = setTimeout(() => resolve(fallback), 350); }),
    ]);
  } finally { clearTimeout(deadline); }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(ASSET_CACHE);
  // Release assets are public and same-origin. A server's Vary: Origin must
  // not distinguish a precache fetch from a module/CSS request after reload.
  // API and controlled-document requests never enter this handler.
  const cached = await cache.match(request, { ignoreVary: true });
  const pathname = new URL(request.url, self.location.origin).pathname;
  // A content hash (or PDF.js version) identifies immutable bytes. Re-fetching
  // these on every cached navigation competes with API calls on weak links.
  const immutable = /^\/assets\/.+-[A-Za-z0-9_-]{8,}\.(?:m?js|css|woff2?|svg|png|webp)$/.test(pathname)
    || /^\/pdfjs\/[^/]+\//.test(pathname);
  if (cached && immutable) return cached;
  const networkPromise = fetch(request)
    .then(async (response) => {
      if (response.ok) await cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);
  if (cached) {
    // Logos and headers should paint instantly from cache while refreshing quietly.
    void networkPromise;
    return cached;
  }
  const fresh = await networkPromise;
  if (fresh) return fresh;
  // A still-open older tab might reference a hashed chunk from the previous
  // deployment. Serve only explicitly cached immutable assets.
  const priorNames = (await caches.keys())
    .filter((name) => name.startsWith("amo-portal-assets-") && name !== ASSET_CACHE)
    .sort().reverse();
  for (const name of priorNames) {
    const fallback = await (await caches.open(name)).match(request, { ignoreVary: true });
    if (fallback) return fallback;
  }
  return Response.error();
}

function looksLikeCachedStatic(url) {
  return typeof url === "string"
    && (
      url.startsWith("/assets/")
      || url.startsWith("/pdfjs/")
      || /\.(?:svg|png|jpe?g|webp|gif|ico|woff2?)$/i.test(url)
      || [
        "/portal-icon.svg",
        "/login-illustration-placeholder.svg",
        "/portal.webmanifest",
        "/manuals-reader.webmanifest",
      ].includes(url)
    );
}

async function precacheStaticShell() {
  if (staticShellWarmup) return staticShellWarmup;
  staticShellWarmup = (async () => {
    const [shellCache, assetCache] = await Promise.all([
      caches.open(SHELL_CACHE),
      caches.open(ASSET_CACHE),
    ]);
    const urls = [...SHELL_URLS];
    try {
      const response = await fetch("/portal-precache.json", { cache: "no-store" });
      if (response.ok) {
        const manifest = await response.json();
        for (const url of [...(manifest.urls || []), ...(manifest.staticUrls || [])]) {
          if (looksLikeCachedStatic(url)) urls.push(url);
        }
      }
    } catch {
      // Keep the minimal shell warm even when the manifest is briefly unavailable.
    }
    await precacheWithBoundedConcurrency([...new Set(urls)].slice(0, 40), shellCache, assetCache, 3);
  })().finally(() => { staticShellWarmup = null; });
  return staticShellWarmup;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isApiRequest(url)) return;

  if (request.mode === "navigate") {
    event.respondWith(cachedShellNavigation(request, event.preloadResponse, event));
    return;
  }
  if (isStaticAsset(request, url)) {
    event.respondWith(cacheFirstAsset(request));
  }
});
