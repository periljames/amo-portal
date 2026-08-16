import { apiRequest, qmsPath } from "./apiClient";

export type AuditDocumentRequestStatus = "REQUESTED" | "UPLOADED" | "ACCEPTED" | "REJECTED" | "WAIVED";

export type AuditDocumentRequest = {
  id: string;
  amo_id: string;
  audit_id: string;
  title: string;
  description: string | null;
  due_date: string | null;
  status: AuditDocumentRequestStatus;
  requested_by_user_id: string | null;
  uploaded_by_user_id: string | null;
  uploaded_at: string | null;
  file_ref: string | null;
  review_note: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditDocumentRequestCreate = {
  title: string;
  description?: string | null;
  due_date?: string | null;
};

export type AuditDocumentRequestUpdate = Partial<{
  title: string;
  description: string | null;
  due_date: string | null;
  status: AuditDocumentRequestStatus;
  file_ref: string | null;
  review_note: string | null;
}>;

export function listAuditDocumentRequests(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditDocumentRequest[]>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/document-requests`), {
    timeoutMs: 15_000,
    cacheTtlMs: 1_500,
    signal,
  });
}

export function createAuditDocumentRequest(amoCode: string, auditId: string, payload: AuditDocumentRequestCreate) {
  return apiRequest<AuditDocumentRequest>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/document-requests`), {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 30_000,
  });
}

export function updateAuditDocumentRequest(amoCode: string, auditId: string, requestId: string, payload: AuditDocumentRequestUpdate) {
  return apiRequest<AuditDocumentRequest>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/document-requests/${encodeURIComponent(requestId)}`), {
    method: "PATCH",
    body: JSON.stringify(payload),
    timeoutMs: 30_000,
  });
}
