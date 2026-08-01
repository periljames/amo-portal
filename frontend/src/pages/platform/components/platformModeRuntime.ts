const PLATFORM_MODE_KEY = "amo_platform_data_mode";
const VALID_MODES = new Set(["REAL", "DEMO"]);

declare global {
  interface Window {
    __amoPlatformModeRuntimeInstalled?: boolean;
  }
}

function storedMode(): "REAL" | "DEMO" {
  const stored = window.localStorage.getItem(PLATFORM_MODE_KEY)?.toUpperCase();
  return stored === "DEMO" ? "DEMO" : "REAL";
}

function normalizePlatformUrl(input: string | URL | null | undefined): string | URL | null | undefined {
  if (input === null || input === undefined) return input;
  let parsed: URL;
  try {
    parsed = new URL(String(input), window.location.href);
  } catch {
    return input;
  }
  if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith("/platform")) return input;

  const explicit = parsed.searchParams.get("mode")?.toUpperCase();
  if (explicit && VALID_MODES.has(explicit)) {
    window.localStorage.setItem(PLATFORM_MODE_KEY, explicit);
    parsed.searchParams.set("mode", explicit);
  } else {
    parsed.searchParams.set("mode", storedMode());
  }
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

function installPlatformModeRuntime(): void {
  if (typeof window === "undefined" || window.__amoPlatformModeRuntimeInstalled) return;
  window.__amoPlatformModeRuntimeInstalled = true;

  const originalPushState = window.history.pushState.bind(window.history);
  const originalReplaceState = window.history.replaceState.bind(window.history);

  window.history.pushState = ((data: unknown, unused: string, url?: string | URL | null) => {
    originalPushState(data, unused, normalizePlatformUrl(url));
  }) as History["pushState"];
  window.history.replaceState = ((data: unknown, unused: string, url?: string | URL | null) => {
    originalReplaceState(data, unused, normalizePlatformUrl(url));
  }) as History["replaceState"];

  if (window.location.pathname.startsWith("/platform")) {
    const current = new URL(window.location.href);
    const explicit = current.searchParams.get("mode")?.toUpperCase();
    if (explicit && VALID_MODES.has(explicit)) {
      window.localStorage.setItem(PLATFORM_MODE_KEY, explicit);
    } else {
      current.searchParams.set("mode", storedMode());
      originalReplaceState(window.history.state, "", `${current.pathname}${current.search}${current.hash}`);
      window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
    }
  }
}

installPlatformModeRuntime();

export {};
