import { apiRequest, qmsPath } from "./apiClient";

export type PreparationAuditSummary = {
  id: string;
  audit_ref: string;
  title: string;
  status?: string | null;
  kind?: string | null;
  domain?: string | null;
  audit_scope_id?: string | null;
  scope?: string | null;
  criteria?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  actual_start?: string | null;
  actual_end?: string | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  location?: string | null;
};

export type PreparationFinding = {
  id: string;
  audit_id: string;
  finding_ref?: string | null;
  title?: string | null;
  description?: string | null;
  severity?: string | null;
  classification?: string | null;
  status?: string | null;
  requirement_ref?: string | null;
  closed_at?: string | null;
  created_at?: string | null;
};

export type AuditPreparationContext = {
  as_of: string;
  audit: PreparationAuditSummary;
  prior_audit_history: { items: PreparationAuditSummary[]; matching_basis: string };
  prior_findings: { items: PreparationFinding[]; classification_counts: Record<string, number>; total: number };
  car_exposure: { items: Array<Record<string, unknown>>; open_count: number; total: number };
  current_findings: PreparationFinding[];
  document_requests: Array<Record<string, unknown>>;
  opening_meeting_records: Array<Record<string, unknown>>;
  controlled_preparation: {
    latest_revision?: { id: string; revision_no: number; status: string; source_fingerprint: string; issued_at?: string | null; change_reason: string } | null;
    checklist_bindings: Array<{ id: string; template_code: string; revision_no: number; content_sha256: string; applied_at: string; application_reason: string }>;
    source_references: unknown[];
  };
  source_lineage: {
    planner_schedule_id?: string | null;
    items: Array<{ source_type: string; source_id: string; source_route?: string | null; rationale: string; source_snapshot: Record<string, unknown> }>;
  };
  cross_source_assurance_pressure: {
    factors: Array<{ code: string; label: string; value: unknown; source: string; hard_requirement: boolean; rationale: string }>;
    authoritative_metrics: Record<string, number>;
    reliability: Record<string, number>;
    statement: string;
  };
  regulatory_and_manual_basis: { audit_criteria?: string | null; audit_scope?: string | null; source_references: unknown[] };
  data_quality: { warnings: Array<{ source: string; type: string; message: string }>; statement: string };
};

export function getAuditPreparationContext(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditPreparationContext>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/preparation-context`), {
    timeoutMs: 20_000,
    cacheTtlMs: 3_000,
    signal,
  });
}
