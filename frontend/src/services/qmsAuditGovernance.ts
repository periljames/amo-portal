import { apiRequest, qmsPath } from "./apiClient";
import { apiBlob } from "./typedApi";

export type AuditPreparationRevision = {
  id: string;
  audit_id: string;
  revision_no: number;
  status: "DRAFT" | "ISSUED";
  preparation_scope?: string | null;
  audit_snapshot: Record<string, unknown>;
  checklist_snapshot: Array<Record<string, unknown>>;
  document_request_snapshot: Array<Record<string, unknown>>;
  source_references: Array<Record<string, unknown>>;
  source_fingerprint: string;
  change_reason: string;
  supersedes_revision_id?: string | null;
  issued_by_user_id?: string | null;
  issued_at?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  events: Array<{ id: string; event_type: string; reason: string; actor_user_id?: string | null; created_at: string }>;
};

export type AuditNoticePolicy = {
  id: string;
  policy_code: string;
  title: string;
  audit_kind?: string | null;
  minimum_notice_days: number;
  review_required: boolean;
  acknowledgement_required: boolean;
  emergency_exception_allowed: boolean;
  unannounced_exception_allowed: boolean;
  is_active: boolean;
};

export type AuditNotice = {
  id: string;
  audit_id: string;
  policy_id?: string | null;
  revision_no: number;
  status: "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "GENERATED" | "DELIVERED" | "ACKNOWLEDGED" | "SUPERSEDED" | "CANCELLED";
  required_notice_days: number;
  notice_date: string;
  exception_type?: "EMERGENCY" | "UNANNOUNCED" | null;
  exception_reason?: string | null;
  subject: string;
  body: string;
  audit_snapshot: Record<string, unknown>;
  recipient_snapshot: Array<Record<string, unknown>>;
  delivery_channel?: string | null;
  delivery_reference?: string | null;
  supersedes_notice_id?: string | null;
  approved_at?: string | null;
  generated_at?: string | null;
  delivered_at?: string | null;
  acknowledged_at?: string | null;
  created_at: string;
  artifact?: {
    id: string;
    source_type: "GENERATED" | "UPLOADED";
    filename: string;
    content_type: string;
    size_bytes: number;
    sha256: string;
    signed_by_user_id?: string | null;
    signed_by_name?: string | null;
    signed_by_title?: string | null;
    signed_at?: string | null;
    created_at: string;
  } | null;
  events: Array<{ id: string; event_type: string; reason: string; created_at: string }>;
};

export type AuditNoticeSubmitResult = {
  notice: AuditNotice;
  delivery_complete: boolean;
  dispatch: {
    attempted: number;
    sent: number;
    failed: number;
    items: Array<{ email: string; role?: string | null; status: string; message_id?: string | null; error?: string | null }>;
  };
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listAuditPreparationRevisions(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditPreparationRevision[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/preparation-revisions`),
    { timeoutMs: 15_000, cacheTtlMs: 0, signal },
  );
}

export function createAuditPreparationRevision(
  amoCode: string,
  auditId: string,
  payload: { reason: string; preparation_scope?: string },
) {
  return apiRequest<AuditPreparationRevision>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/preparation-revisions`),
    json("POST", payload),
  );
}

export function issueAuditPreparationRevision(amoCode: string, auditId: string, revisionId: string, reason: string) {
  return apiRequest<AuditPreparationRevision>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/preparation-revisions/${encodeURIComponent(revisionId)}/issue`),
    json("POST", { reason }),
  );
}

export function listAuditNoticePolicies(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditNoticePolicy[] }>(
    qmsPath(amoCode, "/audit-notice-policies?active_only=true"),
    { timeoutMs: 15_000, cacheTtlMs: 0, signal },
  );
}

export function createAuditNoticePolicy(
  amoCode: string,
  payload: {
    policy_code: string;
    title: string;
    audit_kind?: string | null;
    minimum_notice_days: number;
    review_required: boolean;
    acknowledgement_required: boolean;
    emergency_exception_allowed: boolean;
    unannounced_exception_allowed: boolean;
  },
) {
  return apiRequest<AuditNoticePolicy>(qmsPath(amoCode, "/audit-notice-policies"), json("POST", payload));
}

export function listAuditNotices(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditNotice[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices`),
    { timeoutMs: 15_000, cacheTtlMs: 0, signal },
  );
}

export function createAuditNotice(
  amoCode: string,
  auditId: string,
  payload: {
    policy_id?: string;
    notice_date: string;
    exception_type?: "EMERGENCY" | "UNANNOUNCED";
    exception_reason?: string;
    subject?: string;
    body?: string;
    reason: string;
  },
) {
  return apiRequest<AuditNotice>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices`), json("POST", payload));
}

export function reviseAuditNotice(
  amoCode: string,
  auditId: string,
  noticeId: string,
  payload: {
    policy_id?: string;
    notice_date: string;
    exception_type?: "EMERGENCY" | "UNANNOUNCED";
    exception_reason?: string;
    subject?: string;
    body?: string;
    reason: string;
  },
) {
  return apiRequest<AuditNotice>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices/${encodeURIComponent(noticeId)}/revisions`),
    json("POST", payload),
  );
}

export function transitionAuditNotice(
  amoCode: string,
  auditId: string,
  noticeId: string,
  payload: { action: "SUBMIT" | "RETURN" | "APPROVE" | "GENERATE" | "DELIVER" | "ACKNOWLEDGE" | "CANCEL"; reason: string; delivery_channel?: string; delivery_reference?: string },
) {
  return apiRequest<AuditNotice>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices/${encodeURIComponent(noticeId)}/transitions`),
    json("POST", payload),
  );
}

export function uploadAuditNoticeAttachment(
  amoCode: string,
  auditId: string,
  noticeId: string,
  file: File,
) {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<AuditNotice>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices/${encodeURIComponent(noticeId)}/attachment`),
    { method: "POST", body: form, timeoutMs: 90_000, offline: { queueMutation: false } },
  );
}

export function previewAuditNoticePdf(amoCode: string, auditId: string, noticeId: string) {
  return apiBlob(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices/${encodeURIComponent(noticeId)}/preview`),
    { headers: { Accept: "application/pdf" } },
  );
}

export function downloadAuditNoticeDocument(amoCode: string, auditId: string, noticeId: string) {
  return apiBlob(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices/${encodeURIComponent(noticeId)}/document`),
    { headers: { Accept: "application/pdf" } },
  );
}

export function submitAuditNotice(
  amoCode: string,
  auditId: string,
  noticeId: string,
  reason: string,
) {
  return apiRequest<AuditNoticeSubmitResult>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/notices/${encodeURIComponent(noticeId)}/submit`),
    json("POST", { reason }),
  );
}
