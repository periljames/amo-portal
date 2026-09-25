import { apiRequest, qmsPath } from "./apiClient";
import type { PublicationUploadPayload } from "./publications";

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
  canonical_document_id?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  revisions?: ChecklistTemplateRevision[];
};

export type DmsChecklistLibraryItem = {
  document_id: string;
  code: string;
  title: string;
  document_type: "CHECKLIST" | "FORM";
  hierarchy_path?: string | null;
  owner_department?: string | null;
  current_revision: {
    id: string;
    issue_number?: string | null;
    revision_number: string;
    effective_date?: string | null;
    source_filename?: string | null;
    source_sha256?: string | null;
  };
  reason?: string;
  usage_count?: number;
};

export type DmsChecklistLibrary = {
  items: DmsChecklistLibraryItem[];
  pending?: Array<{
    document_id: string;
    code: string;
    title: string;
    revision_id: string;
    workflow_id: string;
    state: string;
    updated_at?: string | null;
    review_url: string;
  }>;
  recommendation?: DmsChecklistLibraryItem | null;
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

export type ChecklistAIDraft = {
  draft: {
    title: string;
    description: string;
    category: string;
    audit_kind: string;
    items: ChecklistTemplateItem[];
    source_references: Array<Record<string, unknown>>;
  };
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  request_id: string;
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

export function retireChecklistTemplate(amoCode: string, templateId: string) {
  return apiRequest<{ id: string; status: string }>(
    qmsPath(amoCode, `/audit-checklist-templates/${encodeURIComponent(templateId)}`),
    { method: "DELETE", timeoutMs: 15_000 },
  );
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

export function createRealtimeAuditChecklist(
  amoCode: string,
  auditId: string,
  payload: {
    title: string;
    description?: string | null;
    reason: string;
    items: ChecklistTemplateItem[];
    canonical_document_id?: string | null;
    canonical_revision_id?: string | null;
    allow_existing_items: boolean;
  },
) {
  return apiRequest<ChecklistBinding>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklists/realtime`),
    json("POST", payload),
  );
}

export function generateChecklistDraft(
  amoCode: string,
  payload: {
    source_document_ids: string[];
    title: string;
    audit_kind: string;
    focus?: string;
    max_items: number;
  },
) {
  return apiRequest<ChecklistAIDraft>(
    qmsPath(amoCode, "/audit-checklist-templates/ai-draft"),
    { ...json("POST", payload), timeoutMs: 120_000 },
  );
}

export function listCurrentDmsChecklists(
  amoCode: string,
  auditId: string,
  filters: { q?: string; documentType?: "CHECKLIST" | "FORM" } = {},
  signal?: AbortSignal,
) {
  const query = new URLSearchParams();
  if (filters.q?.trim()) query.set("q", filters.q.trim());
  if (filters.documentType) query.set("document_type", filters.documentType);
  const suffix = query.toString() ? `?${query}` : "";
  return apiRequest<DmsChecklistLibrary>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-library${suffix}`), {
    timeoutMs: 15_000,
    cacheTtlMs: 5_000,
    signal,
  });
}

export function bindCurrentDmsChecklist(
  amoCode: string,
  auditId: string,
  documentId: string,
  reason: string,
  allowExistingItems: boolean,
) {
  return apiRequest<ChecklistBinding>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-library/${encodeURIComponent(documentId)}/bind-current`),
    json("POST", { reason, allow_existing_items: allowExistingItems }),
  );
}

export function uploadDmsChecklistFromAudit(
  amoCode: string,
  auditId: string,
  payload: PublicationUploadPayload,
) {
  const body = new FormData();
  body.append("code", payload.code);
  body.append("title", payload.title);
  body.append("revision_number", payload.rev_number);
  body.append("issue_number", payload.issue_number || "00");
  if (payload.effective_date) body.append("effective_date", payload.effective_date);
  body.append("owner_department", payload.owner_role || "QUALITY");
  body.append("reason", payload.change_log || "Uploaded and registered during governed audit preparation.");
  body.append("control_metadata_json", JSON.stringify(payload.control_metadata || { document_type: "CHECKLIST" }));
  body.append("file", payload.file);
  return apiRequest<{
    document: { id: string; code: string; title: string; document_type: string; revision_id: string; revision_status: string; workflow_required: boolean };
    binding: ChecklistBinding | null;
  }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-library/upload`), {
    method: "POST",
    body,
    timeoutMs: 120_000,
  });
}
