import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type DocumentRetentionSourceType = "DOCUMENT" | "REVISION" | "EVIDENCE_ASSET" | "GENERATED_RECORD";
export type DocumentRetentionStatus = "ACTIVE" | "DUE" | "HOLD" | "DISPOSITION_REQUESTED" | "APPROVED" | "REJECTED" | "DISPOSED";

export type DocumentRetentionRecord = {
  id: string;
  tenant_id: string;
  manual_id: string;
  revision_id: string | null;
  source_type: DocumentRetentionSourceType;
  source_id: string | null;
  source_label: string;
  retention_class: string;
  retention_until: string | null;
  status: DocumentRetentionStatus;
  legal_hold: boolean;
  hold_reason: string | null;
  justification: string | null;
  disposition_method: string | null;
  certificate_evidence_asset_id: string | null;
  created_by_user_id: string | null;
  requested_by_user_id: string | null;
  approver_user_id: string | null;
  approved_by_user_id: string | null;
  disposed_by_user_id: string | null;
  requested_at: string | null;
  approved_at: string | null;
  disposed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  metadata: Record<string, unknown>;
};

export type DocumentRetentionApprover = {
  id: string;
  label: string;
  email: string;
  role: string;
};

export type DocumentRetentionSourceItem = {
  id: string;
  label: string;
  status?: string | null;
  revision_id?: string | null;
  sha256?: string | null;
};

export type DocumentRetentionSourceCatalogue = {
  document: { id: string; label: string };
  revisions: DocumentRetentionSourceItem[];
  evidence_assets: DocumentRetentionSourceItem[];
  generated_records: DocumentRetentionSourceItem[];
  bounded: boolean;
  per_type_limit: number;
};

export type DocumentRetentionWorkItem = {
  id: string;
  kind: "RETENTION_APPROVAL" | "RETENTION_EXECUTION";
  title: string;
  detail: string;
  status: string;
  priority: string;
  manual_id: string;
  target_path: string;
  due_at: string | null;
};

function basePath(tenant: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant)}`;
}

async function message(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.clone().json();
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail?.message === "string") return detail.message;
  } catch {
    // Keep fallback.
  }
  return `${fallback} (${response.status}).`;
}

async function request<T>(tenant: string, suffix: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${basePath(tenant)}${suffix}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(await message(response, "Retention request failed"));
  return response.json() as Promise<T>;
}

export async function listDocumentRetention(tenant: string, manualId: string): Promise<DocumentRetentionRecord[]> {
  const payload = await request<{ items?: DocumentRetentionRecord[] }>(
    tenant,
    `/documents/${encodeURIComponent(manualId)}/retention`,
  );
  return Array.isArray(payload.items) ? payload.items : [];
}

export function getDocumentRetentionSources(tenant: string, manualId: string): Promise<DocumentRetentionSourceCatalogue> {
  return request(tenant, `/documents/${encodeURIComponent(manualId)}/retention-sources`);
}

export async function listDocumentRetentionApprovers(tenant: string): Promise<DocumentRetentionApprover[]> {
  const payload = await request<{ items?: DocumentRetentionApprover[] }>(tenant, "/retention-approvers");
  return Array.isArray(payload.items) ? payload.items : [];
}

export async function listDocumentRetentionWork(tenant: string): Promise<DocumentRetentionWorkItem[]> {
  const payload = await request<{ items?: DocumentRetentionWorkItem[] }>(tenant, "/retention-work");
  return Array.isArray(payload.items) ? payload.items : [];
}

export function createDocumentRetention(
  tenant: string,
  payload: {
    manual_id: string;
    source_type: DocumentRetentionSourceType;
    source_id?: string | null;
    retention_class: string;
    retention_until?: string | null;
    metadata?: Record<string, unknown>;
  },
): Promise<DocumentRetentionRecord> {
  return request(tenant, "/retention", { method: "POST", body: JSON.stringify(payload) });
}

export function updateDocumentRetentionHold(
  tenant: string,
  retentionId: string,
  legalHold: boolean,
  reason?: string,
): Promise<DocumentRetentionRecord> {
  return request(tenant, `/retention/${encodeURIComponent(retentionId)}/hold`, {
    method: "PATCH",
    body: JSON.stringify({ legal_hold: legalHold, reason: reason || null }),
  });
}

export function requestDocumentDisposition(
  tenant: string,
  retentionId: string,
  approverUserId: string,
  justification: string,
): Promise<DocumentRetentionRecord> {
  return request(tenant, `/retention/${encodeURIComponent(retentionId)}/request-disposition`, {
    method: "POST",
    body: JSON.stringify({ approver_user_id: approverUserId, justification }),
  });
}

export function decideDocumentDisposition(
  tenant: string,
  retentionId: string,
  decision: "APPROVE" | "REJECT",
  justification: string,
): Promise<DocumentRetentionRecord> {
  return request(tenant, `/retention/${encodeURIComponent(retentionId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, justification }),
  });
}

export function recordDocumentDisposition(
  tenant: string,
  retentionId: string,
  payload: { disposition_method: string; certificate_evidence_asset_id: string; notes?: string },
): Promise<DocumentRetentionRecord> {
  return request(tenant, `/retention/${encodeURIComponent(retentionId)}/dispose`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
