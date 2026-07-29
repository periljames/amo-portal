import { authHeaders, endSession } from "./auth";
import { getApiBaseUrl } from "./config";

export type PlatformConsoleSearchResult = {
  kind: "tenant" | "user" | "support" | "navigation" | string;
  id: string;
  title: string;
  subtitle?: string | null;
  path: string;
  status?: string | null;
};

export type PlatformConsoleBootstrap = Record<string, unknown> & {
  generated_at?: string;
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    credentials: "include",
    headers: { ...authHeaders(), Accept: "application/json" },
  });
  if (response.status === 401) {
    endSession("manual");
    throw new Error("Session expired. Please sign in again.");
  }
  const text = await response.text().catch(() => "");
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail || payload.message : text;
    throw new Error(String(detail || `HTTP ${response.status}`));
  }
  return payload as T;
}

export const platformConsoleApi = {
  bootstrap: () => request<PlatformConsoleBootstrap>("/platform/console/bootstrap"),
  search: (query: string, limit = 12) => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    return request<{ items: PlatformConsoleSearchResult[] }>(`/platform/console/search?${params.toString()}`);
  },
};
