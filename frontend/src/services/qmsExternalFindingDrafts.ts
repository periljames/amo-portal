import { getApiBaseUrl } from "./config";
import type { ExternalAuditorFieldworkItem, ExternalAuditorFieldworkModel, FieldworkFindingLevel, FieldworkFindingSeverity } from "./qmsAuditExternalAccess";

export type ExternalFindingDraftStatus = "CREATED" | "SUBMITTED" | "RETURNED" | "PROMOTED" | "WITHDRAWN";
export type ExternalFindingDraftType = "NON_CONFORMITY" | "OBSERVATION";

export type ExternalFindingDraftEvent = {
  id: string;
  event_type: ExternalFindingDraftStatus;
  reason: string;
  review_note: string | null;
  actor_user_id: string | null;
  actor_participant_id: string | null;
  promoted_finding_id: string | null;
  created_at: string | null;
};

export type ExternalFindingDraft = {
  id: string;
  audit_id: string;
  checklist_item_id: string;
  participant_id: string;
  client_mutation_id: string;
  client_timestamp: string;
  draft_type: ExternalFindingDraftType;
  proposed_severity: FieldworkFindingSeverity;
  proposed_level: FieldworkFindingLevel;
  requirement_ref: string | null;
  description: string;
  objective_evidence: string | null;
  evidence_references: Array<Record<string, unknown> | string>;
  supersedes_draft_id: string | null;
  status: ExternalFindingDraftStatus;
  created_at: string | null;
  events: ExternalFindingDraftEvent[];
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers || {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    if (detail && typeof detail === "object") {
      const objectDetail = detail as Record<string, unknown>;
      throw new Error(typeof objectDetail.message === "string" ? objectDetail.message : `External finding draft request failed with status ${response.status}.`);
    }
    throw new Error(typeof detail === "string" ? detail : `External finding draft request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

function mutationMetadata() {
  const id = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  const deviceKey = "amo:qms:external-fieldwork-device-id";
  const sequenceKey = "amo:qms:external-fieldwork-sequence";
  let deviceId = typeof window !== "undefined" ? window.localStorage.getItem(deviceKey) : null;
  if (!deviceId) {
    deviceId = `qms-external-device-${id}`;
    if (typeof window !== "undefined") window.localStorage.setItem(deviceKey, deviceId);
  }
  const prior = typeof window !== "undefined" ? Number(window.localStorage.getItem(sequenceKey) || "0") : 0;
  const sequence = Math.max(Number.isSafeInteger(prior) ? prior + 1 : 1, Date.now());
  if (typeof window !== "undefined") window.localStorage.setItem(sequenceKey, String(sequence));
  return {
    client_mutation_id: `qms-external-draft-${id}`,
    device_id: deviceId,
    device_sequence: sequence,
    client_timestamp: new Date().toISOString(),
  };
}

export function listMyExternalFindingDrafts() {
  return request<{ items: ExternalFindingDraft[] }>("/quality/audit-access/finding-drafts");
}

export function createExternalFindingDraft(
  model: Pick<ExternalAuditorFieldworkModel, "csrf_token">,
  item: ExternalAuditorFieldworkItem,
  payload: {
    draft_type: ExternalFindingDraftType;
    proposed_severity: FieldworkFindingSeverity;
    proposed_level: FieldworkFindingLevel;
    description: string;
    objective_evidence?: string | null;
    evidence_references?: Array<Record<string, unknown> | string>;
    supersedes_draft_id?: string | null;
  },
) {
  return request<ExternalFindingDraft>(`/quality/audit-access/fieldwork/checklist-items/${encodeURIComponent(item.checklist_item_id)}/finding-drafts`, {
    method: "POST",
    headers: { "X-QMS-CSRF": model.csrf_token },
    body: JSON.stringify({
      ...mutationMetadata(),
      draft_type: payload.draft_type,
      proposed_severity: payload.proposed_severity,
      proposed_level: payload.proposed_level,
      requirement_ref: item.requirement_ref || item.checklist_ref || null,
      description: payload.description,
      objective_evidence: payload.objective_evidence ?? null,
      evidence_references: payload.evidence_references ?? [],
      supersedes_draft_id: payload.supersedes_draft_id ?? null,
    }),
  });
}

export function submitExternalFindingDraft(model: Pick<ExternalAuditorFieldworkModel, "csrf_token">, draftId: string, reason: string) {
  return request<ExternalFindingDraft>(`/quality/audit-access/finding-drafts/${encodeURIComponent(draftId)}/submit`, {
    method: "POST",
    headers: { "X-QMS-CSRF": model.csrf_token },
    body: JSON.stringify({ reason }),
  });
}

export function withdrawExternalFindingDraft(model: Pick<ExternalAuditorFieldworkModel, "csrf_token">, draftId: string, reason: string) {
  return request<ExternalFindingDraft>(`/quality/audit-access/finding-drafts/${encodeURIComponent(draftId)}/withdraw`, {
    method: "POST",
    headers: { "X-QMS-CSRF": model.csrf_token },
    body: JSON.stringify({ reason }),
  });
}
