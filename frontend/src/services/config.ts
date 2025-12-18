// src/services/config.ts
// Shared API config used by auth + CRS + admin user services.

function normaliseBaseUrl(url: string): string {
  const v = (url || "").trim();
  // remove trailing slash so calls like `${API_BASE_URL}/auth/login` don't become //auth/login
  return v.endsWith("/") ? v.slice(0, -1) : v;
}

export const API_BASE_URL = normaliseBaseUrl(
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
);
