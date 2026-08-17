import { apiRequest, qmsPath } from "./apiClient";
import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type { ExternalAuditorFieldworkItem, ExternalAuditorFieldworkModel } from "./qmsAuditExternalAccess";

export type AuditEvidenceArtifact = {
  id: string;
  audit_id: string;
  checklist_item_id: string | null;
  finding_id: string | null;
  source_type: "INTERNAL_USER" | "EXTERNAL_AUDITOR" | "AUDITEE_GUEST";
  filename: string;
  content_type: string | null;
  size_bytes: number;
  sha256: string;
  description: string | null;
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
  options: { baseVersion: number; clientMutationId: string; description?: string | null; findingId?: string | null },
) {
  const form = new FormData();
  form.append("file", file);
  form.append("base_version", String(options.baseVersion));
  form.append("client_mutation_id", options.clientMutationId);
  if (options.description?.trim()) form.append("description", options.description.trim());
  if (options.findingId) form.append("finding_id", options.findingId);
  return apiRequest<{ artifact: AuditEvidenceArtifact; committed_version: number; replayed: boolean }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(checklistItemId)}/evidence`),
    { method: "POST", body: form, timeoutMs: 90_000, offline: { queueWhenOffline: false } },
  );
}

export async function uploadExternalAuditorEvidence(
  model: Pick<ExternalAuditorFieldworkModel, "csrf_token">,
  item: Pick<ExternalAuditorFieldworkItem, "checklist_item_id" | "entity_version">,
  file: File,
  description?: string | null,
) {
  const form = new FormData();
  form.append("file", file);
  form.append("base_version", String(item.entity_version));
  form.append("client_mutation_id", createEvidenceMutationId());
  if (description?.trim()) form.append("description", description.trim());
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
