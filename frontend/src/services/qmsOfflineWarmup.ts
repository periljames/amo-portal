/** Warm code assets after QMS entry; authenticated data stays in scoped IndexedDB. */
export function scheduleQmsOfflineWarmup(): () => void {
  if (typeof navigator === "undefined" || !navigator.serviceWorker) return () => undefined;
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || "")) return () => undefined;
  let stopped = false;
  let timer: number | null = null;
  const schedule = () => {
    if (stopped || timer !== null) return;
    timer = window.setTimeout(() => {
      timer = null;
      if (stopped || navigator.onLine === false || document.visibilityState === "hidden") return;
      void navigator.serviceWorker.ready.then((registration) => {
        if (!stopped) registration.active?.postMessage({ type: "PRECACHE_QMS" });
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
