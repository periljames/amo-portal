import { apiRequest, qmsPath } from "./apiClient";

export type AuditReportRevision = {
  id: string;
  audit_id: string;
  revision_no: number;
  status: "DRAFT" | "INTERNAL_REVIEW" | "APPROVED" | "ISSUED" | "SUPERSEDED" | "CANCELLED";
  filename: string;
  content_type?: string | null;
  size_bytes: number;
  sha256: string;
  report_snapshot: Record<string, unknown>;
  change_reason: string;
  supersedes_revision_id?: string | null;
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  issued_by_user_id?: string | null;
  issued_at?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  events: Array<{ id: string; event_type: string; reason: string; actor_user_id?: string | null; created_at: string }>;
};

export type AuditClosureReadiness = {
  ready: boolean;
  blockers: Array<{ type: string; id?: string; ref?: string | null; reason: string }>;
  counts?: Record<string, number>;
  captured_at: string;
};

export type AuditClosureState = {
  id?: string;
  audit_id: string;
  execution_status: "OPEN" | "CLOSED";
  execution_closed_by_user_id?: string | null;
  execution_closed_at?: string | null;
  execution_close_reason?: string | null;
  execution_evidence_snapshot?: Record<string, unknown>;
  follow_up_status: "OPEN" | "COMPLETE";
  follow_up_completed_by_user_id?: string | null;
  follow_up_completed_at?: string | null;
  follow_up_completion_reason?: string | null;
  follow_up_evidence_snapshot?: Record<string, unknown>;
  execution_readiness: AuditClosureReadiness;
  follow_up_readiness: AuditClosureReadiness;
  events: Array<{ id: string; event_type: string; reason: string; actor_user_id?: string | null; created_at: string }>;
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listAuditReportRevisions(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditReportRevision[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-revisions`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function adoptCurrentAuditReport(amoCode: string, auditId: string, reason: string) {
  return apiRequest<AuditReportRevision>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-revisions/adopt-current`), json("POST", { reason }));
}

export function transitionAuditReport(amoCode: string, auditId: string, revisionId: string, action: "SUBMIT" | "RETURN" | "APPROVE" | "ISSUE" | "CANCEL", reason: string) {
  return apiRequest<AuditReportRevision>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-revisions/${encodeURIComponent(revisionId)}/transitions`), json("POST", { action, reason }));
}

export function getAuditClosureState(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditClosureState>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closure-state`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function recordAuditExecutionClosed(amoCode: string, auditId: string, reason: string) {
  return apiRequest<AuditClosureState>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closure-state/execution-close`), json("POST", { reason }));
}

export function recordAuditFollowUpComplete(amoCode: string, auditId: string, reason: string) {
  return apiRequest<AuditClosureState>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closure-state/follow-up-complete`), json("POST", { reason }));
}

export function reopenAuditFollowUp(amoCode: string, auditId: string, reason: string) {
  return apiRequest<AuditClosureState>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closure-state/reopen-follow-up`), json("POST", { reason }));
}
