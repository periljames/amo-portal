import { apiRequest, qmsPath } from "./apiClient";
import { getToken } from "./auth";
import { getApiBaseUrl } from "./config";

export type ExternalParticipantType = "EXTERNAL_AUDITOR" | "AUDITEE_GUEST";
export type ExternalAuditAssuranceLevel = "EMAIL_LINK" | "MFA" | "PASSKEY";
export type ExternalChecklistResponse = "COMPLIANT" | "NONCOMPLIANT" | "OBSERVATION" | "NOT_APPLICABLE" | "NOT_VERIFIED";

export type ExternalAuditParticipant = {
  id: string;
  audit_id: string;
  participant_type: ExternalParticipantType;
  role: string;
  permissions: string[];
  status: string;
  display_name: string | null;
  email: string | null;
  organisation: string | null;
  assurance_level: ExternalAuditAssuranceLevel | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  active_grant: boolean;
  access_url?: string | null;
};

export type ExternalParticipantCreate = {
  email: string;
  display_name: string;
  organisation?: string | null;
  participant_type: ExternalParticipantType;
  role: string;
  permissions?: string[];
  assurance_level: ExternalAuditAssuranceLevel;
  expires_at: string;
};

export type AuditFindingReleaseState = {
  finding_id: string;
  action: "RELEASED" | "WITHDRAWN";
  include_objective_evidence: boolean;
  released_evidence_refs: Array<Record<string, unknown> | string>;
  reason: string;
  actor_user_id: string | null;
  created_at: string;
};

export type AuditDocumentSubmission = {
  id: string;
  audit_id: string;
  document_request_id: string;
  source_type: "UPLOAD";
  filename: string;
  content_type: string | null;
  size_bytes: number;
  sha256: string;
  response_comment: string | null;
  participant_id: string | null;
  submitted_by_user_id: string | null;
  created_at: string;
};

export type IssuedAuditReportStatus = {
  available: boolean;
  report: {
    id: string;
    revision_no: number;
    filename: string | null;
    content_type: string | null;
    size_bytes: number;
    sha256: string;
    issued_at: string | null;
    acknowledged_at: string | null;
  } | null;
  acknowledgement_statement: string;
};

export type IssuedAuditReportAcknowledgement = {
  report_revision_id: string;
  report_sha256: string;
  acknowledged_at: string;
  acknowledgement_statement: string;
};

export type AuditGuestReadModel = {
  participant: {
    display_name: string | null;
    organisation: string | null;
    participant_type: ExternalParticipantType;
    role: string;
    expires_at: string;
  };
  permissions: string[];
  audit: Partial<{
    id: string;
    audit_ref: string;
    title: string;
    scope: string | null;
    criteria: string | null;
    planned_start: string | null;
    planned_end: string | null;
    actual_start: string | null;
    actual_end: string | null;
  }>;
  progress: { total: number; completed: number; percent: number } | null;
  released_findings: Array<{
    id: string;
    finding_ref: string | null;
    finding_type: string;
    severity: string;
    level: string;
    requirement_ref: string | null;
    description: string;
    objective_evidence: string | null;
    released_evidence_refs: Array<Record<string, unknown> | string>;
    acknowledged_at: string | null;
  }>;
  document_requests: Array<{
    id: string;
    title: string;
    description: string | null;
    due_date: string | null;
    status: string;
    review_note: string | null;
    submitted: boolean;
  }>;
  issued_report_available: boolean;
};

export type ExternalAuditorFieldworkItem = {
  checklist_item_id: string;
  section: string | null;
  checklist_ref: string | null;
  requirement_ref: string | null;
  prompt: string;
  canonical_response_status: ExternalChecklistResponse;
  entity_version: number;
  finding_id: string | null;
  my_auditor_notes: string | null;
  my_evidence_references: Array<Record<string, unknown> | string>;
  my_last_contribution_at: string | null;
  updated_at: string | null;
};

export type ExternalAuditorFieldworkModel = {
  audit_id: string;
  participant_id: string;
  csrf_token: string;
  fieldwork_available: boolean;
  fieldwork_blocker: string | null;
  can_execute_checklist: boolean;
  can_create_evidence: boolean;
  can_draft_findings: boolean;
  finding_draft_blocker: string | null;
  items: ExternalAuditorFieldworkItem[];
};

export type ExternalAuditorMutationResult = {
  client_mutation_id: string;
  committed_version: number;
  replayed: boolean;
  row: ExternalAuditorFieldworkItem;
};

export function listExternalAuditParticipants(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ExternalAuditParticipant[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-participants`), {
    timeoutMs: 15_000,
    cacheTtlMs: 2_000,
    signal,
  });
}

export function createExternalAuditParticipant(amoCode: string, auditId: string, payload: ExternalParticipantCreate) {
  return apiRequest<ExternalAuditParticipant>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-participants`), {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 30_000,
  });
}

export function revokeExternalAuditParticipant(amoCode: string, auditId: string, participantId: string) {
  return apiRequest<ExternalAuditParticipant>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-participants/${encodeURIComponent(participantId)}/revoke`), {
    method: "POST",
    timeoutMs: 30_000,
  });
}

export function listAuditFindingReleases(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditFindingReleaseState[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/finding-releases`), {
    timeoutMs: 15_000,
    cacheTtlMs: 1_500,
    signal,
  });
}

export function releaseAuditFinding(
  amoCode: string,
  auditId: string,
  findingId: string,
  payload: { action: "RELEASED" | "WITHDRAWN"; include_objective_evidence: boolean; released_evidence_refs: Array<Record<string, unknown> | string>; reason: string },
) {
  return apiRequest(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/findings/${encodeURIComponent(findingId)}/release`), {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 30_000,
  });
}

export function listAuditDocumentSubmissions(amoCode: string, auditId: string, requestId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditDocumentSubmission[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/document-requests/${encodeURIComponent(requestId)}/submissions`), {
    timeoutMs: 15_000,
    cacheTtlMs: 1_500,
    signal,
  });
}

export async function downloadAuditDocumentSubmission(amoCode: string, auditId: string, requestId: string, submissionId: string): Promise<Blob> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}${qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/document-requests/${encodeURIComponent(requestId)}/submissions/${encodeURIComponent(submissionId)}/download`)}`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    credentials: "include",
  });
  if (!response.ok) throw new Error(`Document download failed with status ${response.status}.`);
  return response.blob();
}

async function publicRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...(!isFormData && options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    if (detail && typeof detail === "object") {
      const objectDetail = detail as Record<string, unknown>;
      throw new Error(typeof objectDetail.message === "string" ? objectDetail.message : `Audit access request failed with status ${response.status}.`);
    }
    throw new Error(typeof detail === "string" ? detail : `Audit access request failed with status ${response.status}.`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function exchangeAuditGuestToken(token: string) {
  return publicRequest<AuditGuestReadModel>("/quality/audit-access/exchange", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export function getAuditGuestSession() {
  return publicRequest<AuditGuestReadModel>("/quality/audit-access/session");
}

export function getIssuedAuditReportStatus() {
  return publicRequest<IssuedAuditReportStatus>("/quality/audit-access/issued-report");
}

export async function downloadIssuedAuditReport(): Promise<Blob> {
  const response = await fetch(`${getApiBaseUrl()}/quality/audit-access/issued-report/download`, {
    headers: { Accept: "application/pdf,application/octet-stream" },
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `Issued audit report download failed with status ${response.status}.`);
  }
  return response.blob();
}

export function acknowledgeIssuedAuditReport() {
  return publicRequest<IssuedAuditReportAcknowledgement>("/quality/audit-access/issued-report/acknowledge", { method: "POST" });
}

export function getExternalAuditorFieldwork() {
  return publicRequest<ExternalAuditorFieldworkModel>("/quality/audit-access/fieldwork");
}

export function mutateExternalAuditorChecklist(
  model: Pick<ExternalAuditorFieldworkModel, "csrf_token">,
  item: ExternalAuditorFieldworkItem,
  payload: {
    canonical_response_status: ExternalChecklistResponse;
    auditor_notes?: string | null;
    evidence_references?: Array<Record<string, unknown> | string>;
    reason: string;
  },
) {
  const clientMutationId = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `qms-external-fieldwork-${crypto.randomUUID()}`
    : `qms-external-fieldwork-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const deviceIdKey = "amo:qms:external-fieldwork-device-id";
  const deviceSequenceKey = "amo:qms:external-fieldwork-sequence";
  let deviceId = typeof window !== "undefined" ? window.localStorage.getItem(deviceIdKey) : null;
  if (!deviceId) {
    deviceId = `qms-external-device-${clientMutationId.slice(-24)}`;
    if (typeof window !== "undefined") window.localStorage.setItem(deviceIdKey, deviceId);
  }
  const priorSequence = typeof window !== "undefined" ? Number(window.localStorage.getItem(deviceSequenceKey) || "0") : 0;
  const deviceSequence = Math.max(Number.isSafeInteger(priorSequence) ? priorSequence + 1 : 1, Date.now());
  if (typeof window !== "undefined") window.localStorage.setItem(deviceSequenceKey, String(deviceSequence));

  return publicRequest<ExternalAuditorMutationResult>(`/quality/audit-access/fieldwork/checklist-items/${encodeURIComponent(item.checklist_item_id)}/mutations`, {
    method: "POST",
    headers: { "X-QMS-CSRF": model.csrf_token },
    body: JSON.stringify({
      client_mutation_id: clientMutationId,
      device_id: deviceId,
      device_sequence: deviceSequence,
      client_timestamp: new Date().toISOString(),
      base_version: item.entity_version,
      operation: "CHECKLIST_UPDATE",
      canonical_response_status: payload.canonical_response_status,
      auditor_notes: payload.auditor_notes ?? null,
      evidence_references: payload.evidence_references ?? [],
      reason: payload.reason,
    }),
  });
}

export function acknowledgeGuestFinding(findingId: string) {
  return publicRequest<{ finding_id: string; acknowledged_at: string }>(`/quality/audit-access/findings/${encodeURIComponent(findingId)}/acknowledge`, { method: "POST" });
}

export function submitAuditGuestDocument(requestId: string, file: File, responseComment?: string) {
  const form = new FormData();
  form.append("file", file);
  if (responseComment?.trim()) form.append("response_comment", responseComment.trim());
  return publicRequest<AuditDocumentSubmission>(`/quality/audit-access/document-requests/${encodeURIComponent(requestId)}/submit`, {
    method: "POST",
    body: form,
  });
}

export function endAuditGuestSession() {
  return publicRequest<void>("/quality/audit-access/session", { method: "DELETE" });
}
