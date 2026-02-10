import { apiGet } from "./crs";
import { authHeaders } from "./auth";

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

export async function listEventHistory(params?: {
  cursor?: string;
  limit?: number;
  entityType?: string;
  entityId?: string;
  timeStart?: string;
  timeEnd?: string;
}): Promise<ActivityHistoryResponse> {
  const qs = new URLSearchParams();
  if (params?.cursor) qs.set("cursor", params.cursor);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.entityType) qs.set("entityType", params.entityType);
  if (params?.entityId) qs.set("entityId", params.entityId);
  if (params?.timeStart) qs.set("timeStart", params.timeStart);
  if (params?.timeEnd) qs.set("timeEnd", params.timeEnd);
  const path = qs.toString() ? `/events/history?${qs.toString()}` : "/events/history";
  return apiGet<ActivityHistoryResponse>(path, { headers: authHeaders() });
}
