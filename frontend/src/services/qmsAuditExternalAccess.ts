import { apiRequest, qmsPath } from "./apiClient";
import { getApiBaseUrl } from "./config";

export type ExternalParticipantType = "EXTERNAL_AUDITOR" | "AUDITEE_GUEST";
export type ExternalAuditAssuranceLevel = "EMAIL_LINK" | "MFA" | "PASSKEY";

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
    body: payload,
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
    body: payload,
    timeoutMs: 30_000,
  });
}

async function publicRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : `Audit access request failed with status ${response.status}.`);
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

export function acknowledgeGuestFinding(findingId: string) {
  return publicRequest<{ finding_id: string; acknowledged_at: string }>(`/quality/audit-access/findings/${encodeURIComponent(findingId)}/acknowledge`, { method: "POST" });
}

export function endAuditGuestSession() {
  return publicRequest<void>("/quality/audit-access/session", { method: "DELETE" });
}
