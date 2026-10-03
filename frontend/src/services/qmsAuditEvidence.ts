import { apiRequest, qmsPath } from "./apiClient";
import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type { ExternalAuditorFieldworkItem, ExternalAuditorFieldworkModel } from "./qmsAuditExternalAccess";
import { qmsFieldworkDeviceId } from "./qmsChecklistExecutionGovernance";

export type AuditEvidenceContext = {
  location_ref?: string;
  person_ref?: string;
  facility_ref?: string;
  asset_ref?: string;
  tool_ref?: string;
  component_ref?: string;
  regulation_refs?: string[];
  procedure_refs?: string[];
  document_revision_ids?: string[];
};

export type AuditEvidenceArtifact = {
  id: string;
  audit_id: string;
  checklist_item_id: string | null;
  finding_id: string | null;
  evidence_request_id?: string | null;
  source_type: "INTERNAL_USER" | "EXTERNAL_AUDITOR" | "AUDITEE_GUEST";
  filename: string;
  content_type: string | null;
  size_bytes: number;
  sha256: string;
  description: string | null;
  context: AuditEvidenceContext;
  source_device_id?: string | null;
  captured_at?: string | null;
  offline_upload_state?: "SYNCED" | "PENDING" | "FAILED" | "CONFLICT";
  server_processing_state?: "AVAILABLE" | "PROCESSING" | "FAILED";
  uploaded_by_user_id: string | null;
  uploaded_by_participant_id: string | null;
  created_at: string | null;
};

export function listAuditEvidence(amoCode: string, auditId: string, checklistItemId?: string | null, findingId?: string | null, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (checklistItemId) params.set("checklist_item_id", checklistItemId);
  if (findingId) params.set("finding_id", findingId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<{ items: AuditEvidenceArtifact[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/evidence${suffix}`), {
    timeoutMs: 15_000,
    cacheTtlMs: 1_000,
    signal,
  });
}

function appendEvidenceContext(form: FormData, context?: AuditEvidenceContext | null): void {
  if (!context) return;
  for (const key of ["location_ref", "person_ref", "facility_ref", "asset_ref", "tool_ref", "component_ref"] as const) {
    const value = context[key]?.trim();
    if (value) form.append(key, value);
  }
  if (context.regulation_refs?.length) form.append("regulation_refs_json", JSON.stringify(context.regulation_refs));
  if (context.procedure_refs?.length) form.append("procedure_refs_json", JSON.stringify(context.procedure_refs));
  if (context.document_revision_ids?.length) form.append("document_revision_ids_json", JSON.stringify(context.document_revision_ids));
}

export function createEvidenceMutationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `qms-evidence-${crypto.randomUUID()}`
    : `qms-evidence-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function uploadInternalAuditEvidence(
  amoCode: string,
  auditId: string,
  checklistItemId: string,
  file: File,
  options: { baseVersion: number; clientMutationId: string; description?: string | null; findingId?: string | null; evidenceRequestId?: string | null; capturedAt?: string; deviceId?: string; context?: AuditEvidenceContext },
) {
  const form = new FormData();
  form.append("file", file);
  form.append("base_version", String(options.baseVersion));
  form.append("client_mutation_id", options.clientMutationId);
  if (options.description?.trim()) form.append("description", options.description.trim());
  if (options.findingId) form.append("finding_id", options.findingId);
  if (options.evidenceRequestId) form.append("evidence_request_id", options.evidenceRequestId);
  appendEvidenceContext(form, options.context);
  form.append("source_device_id", options.deviceId || qmsFieldworkDeviceId());
  form.append("captured_at", options.capturedAt || new Date(file.lastModified || Date.now()).toISOString());
  return apiRequest<{ artifact: AuditEvidenceArtifact; committed_version: number; replayed: boolean }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(checklistItemId)}/evidence`),
    { method: "POST", body: form, timeoutMs: 90_000, offline: { queueMutation: false } },
  );
}

export async function uploadExternalAuditorEvidence(
  model: Pick<ExternalAuditorFieldworkModel, "csrf_token">,
  item: Pick<ExternalAuditorFieldworkItem, "checklist_item_id" | "entity_version">,
  file: File,
  description?: string | null,
  clientMutationId = createEvidenceMutationId(),
  context?: AuditEvidenceContext | null,
) {
  const form = new FormData();
  form.append("file", file);
  form.append("base_version", String(item.entity_version));
  form.append("client_mutation_id", clientMutationId);
  if (description?.trim()) form.append("description", description.trim());
  appendEvidenceContext(form, context);
  form.append("source_device_id", qmsFieldworkDeviceId());
  form.append("captured_at", new Date(file.lastModified || Date.now()).toISOString());
  const response = await fetch(
    `${getApiBaseUrl()}/quality/audit-access/fieldwork/checklist-items/${encodeURIComponent(item.checklist_item_id)}/evidence`,
    {
      method: "POST",
      headers: { Accept: "application/json", "X-QMS-CSRF": model.csrf_token },
      credentials: "include",
      body: form,
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string"
        ? String((detail as { message: unknown }).message)
        : `External evidence upload failed with status ${response.status}.`;
    throw new Error(message);
  }
  return response.json() as Promise<{ artifact: AuditEvidenceArtifact; committed_version: number; replayed: boolean }>;
}

export async function downloadInternalAuditEvidence(amoCode: string, auditId: string, artifactId: string): Promise<Blob> {
  const path = qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/evidence/${encodeURIComponent(artifactId)}/download`);
  const response = await fetch(`${getApiBaseUrl()}${path}`, { headers: authHeaders({ Accept: "application/octet-stream" }), credentials: "include" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `Evidence download failed with status ${response.status}.`);
  }
  return response.blob();
}

export async function downloadPublicReleasedAuditEvidence(findingId: string, artifactId: string): Promise<Blob> {
  const response = await fetch(
    `${getApiBaseUrl()}/quality/audit-access/findings/${encodeURIComponent(findingId)}/evidence/${encodeURIComponent(artifactId)}/download`,
    { headers: { Accept: "application/octet-stream" }, credentials: "include" },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `Released evidence download failed with status ${response.status}.`);
  }
  return response.blob();
}