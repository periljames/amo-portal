import { apiRequest, qmsPath } from "./apiClient";

export type ChecklistFindingTrigger = "NONE" | "NONCOMPLIANT" | "OBSERVATION" | "ADVERSE_RESPONSE";

export type ChecklistTemplateItem = {
  section?: string | null;
  category?: string | null;
  checklist_ref?: string | null;
  requirement_ref?: string | null;
  regulatory_source_ref?: string | null;
  manual_source_ref?: string | null;
  prompt: string;
  expected_evidence?: string | null;
  response_type: string;
  applicability: string;
  mandatory?: boolean;
  finding_trigger?: ChecklistFindingTrigger;
  sort_order: number;
};

export type ChecklistTemplateRevision = {
  id: string;
  template_id: string;
  revision_no: number;
  status: "DRAFT" | "ISSUED";
  items: ChecklistTemplateItem[];
  source_references: Array<Record<string, unknown> | string>;
  content_sha256: string;
  change_reason: string;
  supersedes_revision_id?: string | null;
  issued_by_user_id?: string | null;
  issued_at?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
};

export type ChecklistTemplate = {
  id: string;
  template_code: string;
  title: string;
  description?: string | null;
  category?: string | null;
  audit_kind?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  revisions?: ChecklistTemplateRevision[];
};

export type ChecklistBinding = {
  id: string;
  audit_id: string;
  template_id: string;
  template_revision_id: string;
  template_code: string;
  revision_no: number;
  content_sha256: string;
  item_snapshot: ChecklistTemplateItem[];
  source_references: Array<Record<string, unknown> | string>;
  instantiated_item_ids: string[];
  application_reason: string;
  applied_by_user_id?: string | null;
  applied_at: string;
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listChecklistTemplates(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ items: ChecklistTemplate[] }>(qmsPath(amoCode, "/audit-checklist-templates"), { timeoutMs: 15_000, cacheTtlMs: 3_000, signal });
}

export function getChecklistTemplate(amoCode: string, templateId: string, signal?: AbortSignal) {
  return apiRequest<ChecklistTemplate>(qmsPath(amoCode, `/audit-checklist-templates/${encodeURIComponent(templateId)}`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function createChecklistTemplate(amoCode: string, payload: { template_code: string; title: string; description?: string; category?: string; audit_kind?: string }) {
  return apiRequest<ChecklistTemplate>(qmsPath(amoCode, "/audit-checklist-templates"), json("POST", payload));
}

export function createChecklistRevision(amoCode: string, templateId: string, payload: { reason: string; items: ChecklistTemplateItem[]; source_references?: Array<Record<string, unknown> | string> }) {
  return apiRequest<ChecklistTemplateRevision>(qmsPath(amoCode, `/audit-checklist-templates/${encodeURIComponent(templateId)}/revisions`), json("POST", payload));
}

export function issueChecklistRevision(amoCode: string, templateId: string, revisionId: string, reason: string) {
  return apiRequest<ChecklistTemplateRevision>(qmsPath(amoCode, `/audit-checklist-templates/${encodeURIComponent(templateId)}/revisions/${encodeURIComponent(revisionId)}/issue`), json("POST", { reason }));
}

export function listChecklistBindings(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ChecklistBinding[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-bindings`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function applyChecklistRevision(amoCode: string, auditId: string, templateRevisionId: string, reason: string, allowExistingItems: boolean) {
  return apiRequest<ChecklistBinding>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-bindings`), json("POST", {
    template_revision_id: templateRevisionId,
    reason,
    allow_existing_items: allowExistingItems,
  }));
}