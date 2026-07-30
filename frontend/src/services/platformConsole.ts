import {
  authHeaders,
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
} from "./auth";
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
  markSessionActivity(`platform-console:get:start:${path}`);
  const extension = extendSessionIfNeeded(`platform-console:get:${path}`);
  if (extension) await extension;

  const headers = new Headers(authHeaders());
  headers.set("Accept", "application/json");

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    credentials: "include",
    headers,
  });
  if (response.status === 401) {
    handleAuthFailure("platform-console-unauthorized");
    throw new Error("Session expired. Please sign in again.");
  }
  const text = await response.text().catch(() => "");
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new Error(`Platform console route ${path} returned invalid JSON.`);
    }
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object"
      ? (payload as { detail?: unknown; message?: unknown }).detail
        ?? (payload as { detail?: unknown; message?: unknown }).message
      : text;
    throw new Error(String(detail || `HTTP ${response.status}`));
  }
  markSessionActivity(`platform-console:get:ok:${path}`);
  return payload as T;
}

export const platformConsoleApi = {
  bootstrap: () => request<PlatformConsoleBootstrap>("/platform/console/bootstrap"),
  search: (query: string, limit = 12) => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    return request<{ items: PlatformConsoleSearchResult[] }>(`/platform/console/search?${params.toString()}`);
  },
};
