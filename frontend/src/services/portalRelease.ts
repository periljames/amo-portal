export type PortalRelease = { available: boolean; checking: boolean; error: string | null };
let state: PortalRelease = { available: false, checking: false, error: null };
const listeners = new Set<() => void>();
let pending: Promise<void> | null = null;

export const getPortalRelease = () => state;
export const subscribePortalRelease = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
function publish(next: PortalRelease) { state = next; listeners.forEach(listener => listener()); }

export async function checkPortalRelease(): Promise<void> {
  if (pending) return pending;
  pending = (async () => {
    publish({ ...state, checking: true, error: null });
    try {
      const entry = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/index-"]')?.src;
      if (!entry) return;
      const response = await fetch("/portal-precache.json", { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error("Could not check the portal version. Try again when connected.");
      const manifest = await response.json();
      const entries = Array.isArray(manifest.urls) ? manifest.urls.filter((url: unknown): url is string => typeof url === "string" && /^\/assets\/index-[^/]+\.js$/.test(url)) : [];
      if (entries.length !== 1) throw new Error("The portal update is not ready yet. Try again shortly.");
      const styles = new Set(Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')).map(link => link.href));
      const expectedStyles: string[] = manifest.urls.filter((url: unknown): url is string => typeof url === "string" && /^\/assets\/index-[^/]+\.css$/.test(url));
      publish({ available: new URL(entries[0], location.origin).href !== entry || expectedStyles.some(url => !styles.has(new URL(url, location.origin).href)), checking: false, error: null });
    } catch (error) {
      publish({ ...state, checking: false, error: error instanceof Error ? error.message : "Could not check for updates." });
    } finally {
      if (state.checking) publish({ ...state, checking: false });
    }
  })().finally(() => { pending = null; });
  return pending;
}

export async function reloadPortalRelease(): Promise<void> {
  const registration = await navigator.serviceWorker?.getRegistration();
  if (registration?.active) {
    // Refresh the canonical shell before reloading, so a cache-first navigation
    // cannot immediately reopen the superseded application entry.
    await new Promise<void>((resolve, reject) => {
      const channel = new MessageChannel();
      const timer = window.setTimeout(() => { channel.port1.close(); reject(new Error("The portal update is still preparing. Try again shortly.")); }, 12000);
      channel.port1.onmessage = event => {
        window.clearTimeout(timer); channel.port1.close();
        if (event.data?.ok) resolve();
        else reject(new Error("The new portal could not be loaded. Your current page remains open."));
      };
      registration.active!.postMessage({ type: "REFRESH_PORTAL_SHELL" }, [channel.port2]);
    });
  }
  location.reload();
}

export function startPortalReleaseChecks(): () => void {
  const checkVisible = () => { if (document.visibilityState === "visible") void checkPortalRelease(); };
  window.addEventListener("focus", checkVisible);
  window.addEventListener("online", checkVisible);
  document.addEventListener("visibilitychange", checkVisible);
  const timer = window.setInterval(checkVisible, 5 * 60 * 1000);
  checkVisible();
  return () => { window.clearInterval(timer); window.removeEventListener("focus", checkVisible); window.removeEventListener("online", checkVisible); document.removeEventListener("visibilitychange", checkVisible); };
}
