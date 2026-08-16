import { apiRequest, qmsPath } from "./apiClient";

export type AuditRetentionStart = "EXECUTION_CLOSED" | "FOLLOW_UP_COMPLETE";
export type AuditDispositionMode = "PRESERVE_METADATA_DELETE_PACKAGE" | "TRANSFER_PACKAGE" | "NO_DISPOSITION";

export type AuditRetentionPolicy = {
  id: string;
  revision_no: number;
  retention_class: string;
  record_type: "AUDIT_PACKAGE";
  retention_start_event: AuditRetentionStart;
  duration_days?: number | null;
  indefinite: boolean;
  governing_basis: string;
  review_before_disposition: boolean;
  legal_hold_supported: boolean;
  disposition_mode: AuditDispositionMode;
  approving_capability: string;
  created_by_user_id?: string | null;
  created_at: string;
};

export type AuditArchiveManifestItem = {
  id: string;
  item_type: string;
  authoritative_record_id: string;
  revision_ref?: string | null;
  source_system: string;
  content_hash?: string | null;
  retention_role: string;
  metadata: Record<string, unknown>;
};

export type AuditArchiveManifest = {
  id: string;
  audit_id: string;
  manifest_version: number;
  retention_policy_revision_id: string;
  retention_class: string;
  retention_start_at: string;
  retention_due_at?: string | null;
  manifest_sha256: string;
  item_count: number;
  package_filename?: string | null;
  package_content_type?: string | null;
  package_size_bytes?: number | null;
  package_sha256?: string | null;
  package_available?: boolean;
  created_by_user_id?: string | null;
  created_at: string;
  items: AuditArchiveManifestItem[];
};

export type AuditLegalHold = {
  hold_key: string;
  reason: string;
  governing_basis: string;
  created_at: string;
};

export type AuditDispositionState = {
  event_type: "APPROVED" | "REJECTED" | "EXECUTED";
  disposition_mode: AuditDispositionMode;
  inventory_sha256: string;
  package_sha256?: string | null;
  action_ref?: string | null;
  reason: string;
  created_at: string;
};

export type AuditArchiveGovernance = {
  policy: { configured: boolean; current?: AuditRetentionPolicy | null };
  manifest?: AuditArchiveManifest | null;
  active_holds: AuditLegalHold[];
  disposition?: AuditDispositionState | null;
  retention_due: boolean;
};

export type AuditRetentionPolicyCreate = {
  retention_class: string;
  retention_start_event: AuditRetentionStart;
  duration_days?: number | null;
  indefinite: boolean;
  governing_basis: string;
  review_before_disposition: boolean;
  legal_hold_supported: boolean;
  disposition_mode: AuditDispositionMode;
  approving_capability: string;
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function getAuditArchiveGovernance(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditArchiveGovernance>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/archive-governance`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function createAuditRetentionPolicyRevision(amoCode: string, payload: AuditRetentionPolicyCreate) {
  return apiRequest<AuditRetentionPolicy>(
    qmsPath(amoCode, "/audit-retention-policy/revisions"),
    json("POST", payload),
  );
}

export function generateAuditArchiveManifest(amoCode: string, auditId: string) {
  return apiRequest<AuditArchiveManifest>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/archive-manifests/generate`),
    { method: "POST" },
  );
}

export function placeAuditLegalHold(
  amoCode: string,
  auditId: string,
  holdKey: string,
  payload: { reason: string; governing_basis: string; manifest_id?: string | null },
) {
  return apiRequest<{ hold_key: string; event_type: "PLACED"; created_at: string }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/legal-holds/${encodeURIComponent(holdKey)}/place`),
    json("POST", payload),
  );
}

export function releaseAuditLegalHold(
  amoCode: string,
  auditId: string,
  holdKey: string,
  payload: { reason: string; governing_basis: string; manifest_id?: string | null },
) {
  return apiRequest<{ hold_key: string; event_type: "RELEASED"; created_at: string }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/legal-holds/${encodeURIComponent(holdKey)}/release`),
    json("POST", payload),
  );
}

export function reviewAuditDisposition(
  amoCode: string,
  auditId: string,
  manifestId: string,
  approved: boolean,
  reason: string,
) {
  return apiRequest<{ event_type: "APPROVED" | "REJECTED"; inventory_sha256: string; created_at: string }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/archive-manifests/${encodeURIComponent(manifestId)}/disposition-review`),
    json("POST", { approved, reason }),
  );
}

export function executeAuditDisposition(amoCode: string, auditId: string, manifestId: string, reason: string) {
  return apiRequest<{
    event_type: "EXECUTED";
    disposition_mode: AuditDispositionMode;
    inventory_sha256: string;
    package_sha256?: string | null;
    action_ref?: string | null;
    created_at: string;
    authoritative_records_deleted: boolean;
    metadata_preserved: boolean;
  }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/archive-manifests/${encodeURIComponent(manifestId)}/dispose`),
    json("POST", { reason }),
  );
}

export async function downloadAuditArchivePackage(amoCode: string, auditId: string, manifestId: string): Promise<Blob> {
  const path = qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/archive-manifests/${encodeURIComponent(manifestId)}/download`);
  const response = await fetch(path, { credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : `Archive download failed (${response.status}).`);
  }
  return response.blob();
}
