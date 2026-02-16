import { getApiBaseUrl } from "./config";
import { getToken } from "./auth";

export type ActivityEventRead = {
  id: string;
  type: string;
  entityType: string;
  entityId: string;
  action: string;
  timestamp: string;
  actor?: { userId?: string; name?: string; department?: string } | null;
  metadata?: Record<string, unknown>;
};

export type ActivityHistoryResponse = {
  items: ActivityEventRead[];
  next_cursor: string | null;
};

const etagCache = new Map<string, { etag: string; payload: ActivityHistoryResponse }>();

function historyCacheKey(path: string, token: string | null): string {
  return `${path}::${token ?? "anon"}`;
}

function historyPath(params?: {
  cursor?: string;
  limit?: number;
  entityType?: string;
  entityId?: string;
  timeStart?: string;
  timeEnd?: string;
}): string {
  const qs = new URLSearchParams();
  if (params?.cursor) qs.set("cursor", params.cursor);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.entityType) qs.set("entityType", params.entityType);
  if (params?.entityId) qs.set("entityId", params.entityId);
  if (params?.timeStart) qs.set("timeStart", params.timeStart);
  if (params?.timeEnd) qs.set("timeEnd", params.timeEnd);
  return qs.toString() ? `/api/events/history?${qs.toString()}` : "/api/events/history";
}

export async function listEventHistory(params?: {
  cursor?: string;
  limit?: number;
  entityType?: string;
  entityId?: string;
  timeStart?: string;
  timeEnd?: string;
}): Promise<ActivityHistoryResponse> {
  const token = getToken();
  const path = historyPath(params);
  const fullUrl = `${getApiBaseUrl()}${path}`;
  const cacheKey = historyCacheKey(path, token);
  const cached = etagCache.get(cacheKey);
  const res = await fetch(fullUrl, {
    method: "GET",
    credentials: "include",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(cached?.etag ? { "If-None-Match": cached.etag } : {}),
    },
  });

  if (res.status === 304 && cached) {
    return cached.payload;
  }

  if (res.status === 401) {
    // History is auxiliary data for cockpit context; do not force global logout
    // from this endpoint because token propagation races can otherwise cause
    // login/logout loops on quality pages.
    return cached?.payload ?? { items: [], next_cursor: null };
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Events API ${res.status}: ${text || res.statusText}`);
  }

  const payload = (await res.json()) as ActivityHistoryResponse;
  const etag = res.headers.get("etag");
  if (etag) {
    etagCache.set(cacheKey, { etag, payload });
  }
  return payload;
}
