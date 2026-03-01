const CACHE_NAME = "aerodoc-hybrid-dms-v1";
const PRECACHE = [
  "/",
  "/manuals-reader.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

function shouldCache(reqUrl) {
  return (
    reqUrl.pathname.includes("/qms/documents/") ||
    reqUrl.pathname.includes("/qms/aerodoc/") ||
    reqUrl.pathname.endsWith(".js") ||
    reqUrl.pathname.endsWith(".css")
  );
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (!shouldCache(url)) return;

  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
