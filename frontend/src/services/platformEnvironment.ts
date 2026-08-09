export type PlatformDataMode = "REAL" | "DEMO";

const STORAGE_KEY = "amo_platform_data_mode";

function validMode(value: unknown): PlatformDataMode | null {
  const mode = String(value || "").trim().toUpperCase();
  return mode === "REAL" || mode === "DEMO" ? mode : null;
}

export function readPlatformDataMode(search?: string): PlatformDataMode {
  if (search !== undefined) {
    const fromUrl = validMode(new URLSearchParams(search).get("data_mode"));
    if (fromUrl) return fromUrl;
  }
  if (typeof window !== "undefined") {
    const stored = validMode(window.localStorage.getItem(STORAGE_KEY));
    if (stored) return stored;
  }
  return "REAL";
}

export function persistPlatformDataMode(mode: PlatformDataMode): void {
  if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, mode);
}

export function withPlatformDataMode(target: string, mode: PlatformDataMode): string {
  const [pathname, raw = ""] = target.split("?", 2);
  const query = new URLSearchParams(raw);
  query.set("data_mode", mode);
  const encoded = query.toString();
  return encoded ? `${pathname}?${encoded}` : pathname;
}

export function replaceLocationDataMode(pathname: string, search: string, mode: PlatformDataMode): string {
  const query = new URLSearchParams(search);
  query.set("data_mode", mode);
  return `${pathname}?${query.toString()}`;
}
