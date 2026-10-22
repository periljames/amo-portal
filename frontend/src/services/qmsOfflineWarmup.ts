/** Warm code assets; authenticated data stays in scoped IndexedDB. */
function scheduleOfflineWarmup(type: "PRECACHE_QMS" | "PRECACHE_PORTAL"): () => void {
  if (typeof navigator === "undefined" || !navigator.serviceWorker) return () => undefined;
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (connection?.saveData || /^(slow-2g|2g|3g)$/.test(connection?.effectiveType || "")) return () => undefined;
  let stopped = false;
  let timer: number | null = null;
  const schedule = () => {
    if (stopped || timer !== null) return;
    timer = window.setTimeout(() => {
      timer = null;
      if (stopped || navigator.onLine === false || document.visibilityState === "hidden") return;
      void navigator.serviceWorker.ready.then((registration) => {
        if (!stopped) registration.active?.postMessage({ type });
      }).catch(() => undefined);
    }, 10_000 + Math.floor(Math.random() * 20_000));
  };
  schedule();
  window.addEventListener("online", schedule);
  document.addEventListener("visibilitychange", schedule);
  return () => {
    stopped = true;
    if (timer !== null) window.clearTimeout(timer);
    window.removeEventListener("online", schedule);
    document.removeEventListener("visibilitychange", schedule);
  };
}

export const scheduleQmsOfflineWarmup = () => scheduleOfflineWarmup("PRECACHE_QMS");
export const schedulePortalOfflineWarmup = () => scheduleOfflineWarmup("PRECACHE_PORTAL");
