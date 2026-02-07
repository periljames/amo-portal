// src/services/config.ts
// Shared API config used by auth + CRS + admin user services.

export function normaliseBaseUrl(url: string): string {
  const v = (url || "").trim();
  // remove trailing slash so calls like `${API_BASE_URL}/auth/login` don't become //auth/login
  return v.endsWith("/") ? v.slice(0, -1) : v;
}

let apiBaseRuntimeOverride: string | null = null;

export function setApiBaseRuntime(value: string | null) {
  apiBaseRuntimeOverride = value ? normaliseBaseUrl(value) : null;
}

export function getApiBaseUrl(): string {
  if (apiBaseRuntimeOverride) {
    return normaliseBaseUrl(apiBaseRuntimeOverride);
  }
  if (import.meta.env.VITE_API_BASE_URL) {
    return normaliseBaseUrl(import.meta.env.VITE_API_BASE_URL);
  }
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    if (hostname && !["localhost", "127.0.0.1"].includes(hostname)) {
      return normaliseBaseUrl(`${protocol}//${hostname}:8080`);
    }
  }
  return "http://127.0.0.1:8080";
}
