import { apiRequest, qmsPath } from "./apiClient";
import { getApiBaseUrl } from "./config";

export type AuditControlledSourceSystem = "QMS_LOCAL" | "DOCUMENT_CONTROL";

export type ControlledDocumentSubmission = {
  id: string;
  request_id: string;
  source_system: AuditControlledSourceSystem;
  document_id: string;
  revision_id: string | null;
  response_comment: string | null;
  created_at: string;
};

export type CanonicalDocumentControlDocument = {
  id: string;
  code: string;
  title: string;
  manual_type: string;
  status: string;
  current_published_revision_id: string | null;
};

export type CanonicalDocumentControlRevision = {
  id: string;
  document_id: string;
  issue_number: string | null;
  revision_number: string;
  status: string;
  effective_date: string | null;
  source_sha256: string | null;
};

export type GovernedAuditDocumentRequest = {
  id: string;
  audit_id: string;
  title: string;
  description: string | null;
  due_date: string | null;
  status: "REQUESTED" | "UPLOADED" | "ACCEPTED" | "REJECTED" | "WAIVED";
  file_ref: string | null;
  uploaded_at: string | null;
  review_note: string | null;
  created_at: string | null;
  updated_at: string | null;
  request_type: "DOCUMENT" | "RECORD" | "MANUAL" | "FORM" | "CERTIFICATE" | "REGISTER" | "OTHER";
  linked_criterion: string | null;
  is_required: boolean;
  source_mode: "UPLOAD" | "CONTROLLED_DMS" | "UPLOAD_OR_CONTROLLED";
  controlled_source_system: AuditControlledSourceSystem;
  controlled_document_id: string | null;
  controlled_revision_id: string | null;
  canonical_document_id: string | null;
  canonical_revision_id: string | null;
};

export type PublicGovernedAuditDocumentRequest = Omit<GovernedAuditDocumentRequest, "audit_id" | "file_ref" | "uploaded_at" | "created_at" | "updated_at"> & {
  controlled_submission: ControlledDocumentSubmission | null;
};

export type AuditMeeting = {
  id: string;
  audit_id: string;
  meeting_type: "OPENING" | "CLOSING" | "FOLLOW_UP" | "OTHER";
  scheduled_start: string;
  scheduled_end: string | null;
  location: string | null;
  conference_url: string | null;
  status: "PLANNED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
  notes?: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AuditClosingNarrative = {
  conclusion: string | null;
  positive_practices: string | null;
  management_summary: string | null;
  updated_at: string | null;
};

export type PublicAuditCar = {
  id: string;
  car_number: string;
  title: string;
  summary: string;
  priority: string | null;
  status: string | null;
  due_date: string | null;
  target_closure_date: string | null;
  closed_at: string | null;
  finding_id: string;
  finding_ref: string | null;
};

export type PublicAuditCollaboration = {
  meetings: AuditMeeting[];
  cars: PublicAuditCar[];
  closing_narrative: AuditClosingNarrative;
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

async function publicJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string"
        ? String((detail as { message: unknown }).message)
        : `Audit collaboration request failed (${response.status}).`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function listGovernedAuditDocumentRequests(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: GovernedAuditDocumentRequest[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/governed-document-requests`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function listControlledDocumentSubmissions(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ControlledDocumentSubmission[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/controlled-document-submissions`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function listCanonicalDocumentControlDocuments(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: CanonicalDocumentControlDocument[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/document-control/documents`),
    { timeoutMs: 15_000, cacheTtlMs: 30_000, signal },
  );
}

export function listCanonicalDocumentControlRevisions(
  amoCode: string,
  auditId: string,
  documentId: string,
  signal?: AbortSignal,
) {
  return apiRequest<{ items: CanonicalDocumentControlRevision[] }>(
    qmsPath(
      amoCode,
      `/audits/${encodeURIComponent(auditId)}/document-control/documents/${encodeURIComponent(documentId)}/revisions`,
    ),
    { timeoutMs: 15_000, cacheTtlMs: 10_000, signal },
  );
}

export function createGovernedAuditDocumentRequest(
  amoCode: string,
  auditId: string,
  payload: {
    title: string;
    description?: string | null;
    due_date?: string | null;
    request_type: GovernedAuditDocumentRequest["request_type"];
    linked_criterion?: string | null;
    is_required: boolean;
    source_mode: GovernedAuditDocumentRequest["source_mode"];
    controlled_source_system: AuditControlledSourceSystem;
    controlled_document_id?: string | null;
    controlled_revision_id?: string | null;
    canonical_document_id?: string | null;
    canonical_revision_id?: string | null;
  },
) {
  return apiRequest<GovernedAuditDocumentRequest>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/governed-document-requests`), json("POST", payload));
}

export function updateGovernedAuditDocumentRequest(
  amoCode: string,
  auditId: string,
  requestId: string,
  payload: Partial<Pick<GovernedAuditDocumentRequest,
    "status" | "review_note" | "request_type" | "linked_criterion" | "is_required" | "source_mode" |
    "controlled_source_system" | "controlled_document_id" | "controlled_revision_id" |
    "canonical_document_id" | "canonical_revision_id">>,
) {
  return apiRequest<GovernedAuditDocumentRequest>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/governed-document-requests/${encodeURIComponent(requestId)}`),
    json("PATCH", payload),
  );
}

export function listAuditMeetings(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditMeeting[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/meetings`), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function createAuditMeeting(
  amoCode: string,
  auditId: string,
  payload: {
    meeting_type: AuditMeeting["meeting_type"];
    scheduled_start: string;
    scheduled_end?: string | null;
    location?: string | null;
    conference_url?: string | null;
    status?: AuditMeeting["status"];
    notes?: string | null;
  },
) {
  return apiRequest<AuditMeeting>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/meetings`), json("POST", payload));
}

export function updateAuditMeeting(
  amoCode: string,
  auditId: string,
  meetingId: string,
  payload: Partial<Omit<AuditMeeting, "id" | "audit_id" | "created_at" | "updated_at">>,
) {
  return apiRequest<AuditMeeting>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/meetings/${encodeURIComponent(meetingId)}`), json("PATCH", payload));
}

export function getAuditClosingNarrative(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditClosingNarrative>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closing-narrative`), { timeoutMs: 15_000, cacheTtlMs: 1_500, signal });
}

export function updateAuditClosingNarrative(
  amoCode: string,
  auditId: string,
  payload: Pick<AuditClosingNarrative, "conclusion" | "positive_practices" | "management_summary">,
) {
  return apiRequest<AuditClosingNarrative>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closing-narrative`), json("PUT", payload));
}

export function getPublicAuditCollaboration(): Promise<PublicAuditCollaboration> {
  return publicJson<PublicAuditCollaboration>("/quality/audit-access/collaboration");
}

export function listPublicGovernedAuditDocumentRequests() {
  return publicJson<{ items: PublicGovernedAuditDocumentRequest[] }>("/quality/audit-access/governed-document-requests");
}

export function linkPublicControlledDocumentRequest(
  requestId: string,
  payload: {
    source_system: AuditControlledSourceSystem;
    document_id: string;
    revision_id?: string | null;
    response_comment?: string | null;
  },
) {
  return publicJson<ControlledDocumentSubmission>(
    `/quality/audit-access/document-requests/${encodeURIComponent(requestId)}/link-controlled`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
  );
}
