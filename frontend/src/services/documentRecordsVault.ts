import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

function path(tenant: string, suffix: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant.toLowerCase())}${suffix}`;
}

async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${url}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : String(payload?.detail?.message || message);
    } catch {
      // Keep HTTP status fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export type RecordSeries = {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  owner_department: string;
  retention_years: number;
  disposition_method: "REVIEW_AT_EXPIRY" | "ARCHIVE" | "TRANSFER" | "DESTROY";
  restricted: boolean;
  controllers_can_read?: boolean | null;
  status: string;
  content_access: boolean;
};

export type RetainedRecord = {
  id: string;
  series_id: string;
  series_code: string;
  record_number: string;
  title: string;
  source_module?: string | null;
  source_entity_type?: string | null;
  source_entity_id?: string | null;
  filename?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  captured_at?: string | null;
  retention_due_at?: string | null;
  legal_hold: boolean;
  legal_hold_reason?: string | null;
  disposition_status: "ACTIVE" | "ARCHIVED" | "TRANSFERRED" | "DISPOSED";
  content_access: boolean;
  download_url?: string | null;
};

export type RecordsResponse = {
  items: RetainedRecord[];
  pagination: { page: number; per_page: number; total: number; returned: number };
};

export function listRecordSeries(tenant: string): Promise<{ items: RecordSeries[] }> {
  return api(path(tenant, "/records/series"));
}

export function createRecordSeries(
  tenant: string,
  payload: {
    code: string;
    title: string;
    description?: string | null;
    owner_department: string;
    retention_years: number;
    disposition_method: RecordSeries["disposition_method"];
    restricted: boolean;
    controllers_can_read: boolean;
  },
): Promise<RecordSeries> {
  return api(path(tenant, "/records/series"), { method: "POST", body: JSON.stringify(payload) });
}

export function listRecords(
  tenant: string,
  filters: { q?: string; seriesId?: string; sourceModule?: string; legalHold?: boolean; dispositionStatus?: string; retentionDue?: boolean; page?: number; perPage?: number } = {},
): Promise<RecordsResponse> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.seriesId) params.set("series_id", filters.seriesId);
  if (filters.sourceModule) params.set("source_module", filters.sourceModule);
  if (filters.legalHold !== undefined) params.set("legal_hold", String(filters.legalHold));
  if (filters.dispositionStatus) params.set("disposition_status", filters.dispositionStatus);
  if (filters.retentionDue) params.set("retention_due", "true");
  params.set("page", String(filters.page || 1));
  params.set("per_page", String(filters.perPage || 50));
  return api(`${path(tenant, "/records")}?${params.toString()}`);
}

export function getRecord(tenant: string, recordId: string): Promise<RetainedRecord> {
  return api(path(tenant, `/records/${encodeURIComponent(recordId)}`));
}

export function uploadRecord(
  tenant: string,
  payload: { artifact: File; seriesId: string; recordNumber: string; title: string; sourceModule?: string; sourceEntityType?: string; sourceEntityId?: string },
): Promise<RetainedRecord> {
  const body = new FormData();
  body.append("artifact", payload.artifact);
  body.append("series_id", payload.seriesId);
  body.append("record_number", payload.recordNumber);
  body.append("title", payload.title);
  body.append("source_module", payload.sourceModule || "DOCUMENT_CONTROL");
  if (payload.sourceEntityType) body.append("source_entity_type", payload.sourceEntityType);
  if (payload.sourceEntityId) body.append("source_entity_id", payload.sourceEntityId);
  return api(path(tenant, "/records"), { method: "POST", body });
}

export function setRecordLegalHold(tenant: string, recordId: string, enabled: boolean, reason: string): Promise<{ id: string; legal_hold: boolean }> {
  return api(path(tenant, `/records/${encodeURIComponent(recordId)}/legal-hold`), {
    method: "POST",
    body: JSON.stringify({ enabled, reason }),
  });
}

export function disposeRecord(
  tenant: string,
  recordId: string,
  dispositionStatus: "ARCHIVED" | "TRANSFERRED" | "DISPOSED",
  reason: string,
): Promise<{ id: string; disposition_status: string }> {
  return api(path(tenant, `/records/${encodeURIComponent(recordId)}/disposition`), {
    method: "POST",
    body: JSON.stringify({ disposition_status: dispositionStatus, reason, evidence: [] }),
  });
}

export async function downloadRecord(tenant: string, record: RetainedRecord): Promise<void> {
  if (!record.download_url) throw new Error("This record is not available for download.");
  const response = await fetch(`${getApiBaseUrl()}${record.download_url}`, {
    headers: authHeaders(),
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(`Record download failed (${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = record.filename || record.record_number;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
