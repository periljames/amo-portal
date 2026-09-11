import { apiRequest, qmsPath } from "./apiClient";

export type QmsCommandSearchView = "global" | "mine";

export type QmsCommandSearchItem = {
  kind: "audit" | "finding" | "car" | "schedule" | string;
  id: string;
  reference?: string | null;
  title: string;
  subtitle?: string | null;
  status?: string | null;
  path: string;
};

export type QmsCommandSearchResponse = {
  query: string;
  view: QmsCommandSearchView;
  items: QmsCommandSearchItem[];
};

export function searchQmsCommands(
  amoCode: string,
  query: string,
  view: QmsCommandSearchView = "global",
  signal?: AbortSignal,
): Promise<QmsCommandSearchResponse> {
  const params = new URLSearchParams({ q: query.trim(), view, limit: "18" });
  return apiRequest<QmsCommandSearchResponse>(
    qmsPath(amoCode, `/command-search?${params.toString()}`),
    { timeoutMs: 10_000, cacheTtlMs: 2_000, signal },
  );
}
