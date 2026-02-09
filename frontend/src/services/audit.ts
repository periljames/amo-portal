import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";

export interface AuditEvent {
  id: string;
  amo_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_user_id: string | null;
  occurred_at: string;
  created_at: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  correlation_id?: string | null;
}

type QueryVal = string | number | boolean | null | undefined;

const API_BASE = getApiBaseUrl();

function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    qs.set(key, String(value));
  });
  const str = qs.toString();
  return str ? `?${str}` : "";
}

export async function listAuditEvents(params: {
  entityType?: string;
  entityId?: string;
  limit?: number;
}): Promise<AuditEvent[]> {
  const token = getToken();
  const query = toQuery({
    entity_type: params.entityType,
    entity_id: params.entityId,
  });
  const resp = await fetch(`${API_BASE}/audit-events${query}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!resp.ok) {
    if (resp.status === 401) {
      handleAuthFailure();
    }
    if (resp.status === 403) {
      throw new Error("Access denied.");
    }
    throw new Error("Failed to load audit history.");
  }
  const data = (await resp.json()) as AuditEvent[];
  if (params.limit && data.length > params.limit) {
    return data.slice(0, params.limit);
  }
  return data;
}
