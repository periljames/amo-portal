import { apiRequest, qmsPath } from "./apiClient";

export type CanonicalChecklistResponse = "COMPLIANT" | "NONCOMPLIANT" | "OBSERVATION" | "NOT_APPLICABLE" | "NOT_VERIFIED";
export type FieldworkFindingResponse = "NONCOMPLIANT" | "OBSERVATION";
export type FieldworkFindingLevel = "LEVEL_1" | "LEVEL_2" | "LEVEL_3" | "LEVEL_4";
export type FieldworkFindingSeverity = "MINOR" | "MAJOR" | "CRITICAL";

export type ChecklistExecutionGovernanceRow = {
  checklist_item_id: string;
  audit_id: string;
  section?: string | null;
  checklist_ref?: string | null;
  requirement_ref?: string | null;
  prompt: string;
  legacy_response_status: string;
  canonical_response_status: CanonicalChecklistResponse;
  objective_evidence?: string | null;
  finding_id?: string | null;
  auditor_notes?: string | null;
  evidence_references: Array<Record<string, unknown> | string>;
  governance_id?: string | null;
  entity_version: number;
  updated_by_user_id?: string | null;
  updated_at?: string | null;
  events: Array<{
    id: string;
    event_type: "CREATED" | "UPDATED";
    reason: string;
    before_snapshot?: Record<string, unknown> | null;
    after_snapshot: Record<string, unknown>;
    actor_user_id?: string | null;
    created_at: string;
  }>;
};

export type ChecklistExecutionGovernanceResponse = {
  items: ChecklistExecutionGovernanceRow[];
  canonical_response_values: CanonicalChecklistResponse[];
  legacy_compatibility: Record<string, string>;
};

export type FieldworkMutationResult = {
  client_mutation_id: string;
  committed_version: number;
  replayed: boolean;
  row: ChecklistExecutionGovernanceRow;
};

export type AtomicFieldworkFindingResult = FieldworkMutationResult & {
  finding: { id: string; finding_ref?: string | null; [key: string]: unknown };
  car_id?: string | null;
  car_number?: string | null;
};

export type FieldworkMutationPayload = {
  canonical_response_status: CanonicalChecklistResponse;
  auditor_notes?: string | null;
  evidence_references?: Array<Record<string, unknown> | string>;
  reason: string;
};

export type AtomicFieldworkFindingPayload = {
  canonical_response_status: FieldworkFindingResponse;
  severity: FieldworkFindingSeverity;
  level: FieldworkFindingLevel;
  requirement_ref?: string | null;
  description: string;
  objective_evidence?: string | null;
  safety_sensitive?: boolean;
  target_close_date?: string | null;
  auditor_notes?: string | null;
  evidence_references?: Array<Record<string, unknown> | string>;
  reason: string;
};

const FIELDWORK_DEVICE_KEY = "amo:qms:fieldwork-device-id";
const FIELDWORK_SEQUENCE_KEY = "amo:qms:fieldwork-device-sequence";

function randomIdentifier(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`;
}

export function qmsFieldworkDeviceId(): string {
  if (typeof window === "undefined") return randomIdentifier("qms-device");
  const current = window.localStorage.getItem(FIELDWORK_DEVICE_KEY)?.trim();
  if (current) return current;
  const created = randomIdentifier("qms-device");
  window.localStorage.setItem(FIELDWORK_DEVICE_KEY, created);
  return created;
}

export function nextQmsFieldworkDeviceSequence(): number {
  if (typeof window === "undefined") return Date.now();
  const raw = Number(window.localStorage.getItem(FIELDWORK_SEQUENCE_KEY) || "0");
  const prior = Number.isSafeInteger(raw) && raw >= 0 ? raw : 0;
  const next = Math.max(prior + 1, Date.now());
  window.localStorage.setItem(FIELDWORK_SEQUENCE_KEY, String(next));
  return next;
}

export function newQmsFieldworkMutationId(): string {
  return randomIdentifier("qms-fieldwork");
}

function fieldworkEnvelope(clientMutationId: string, baseVersion: number) {
  return {
    client_mutation_id: clientMutationId,
    device_id: qmsFieldworkDeviceId(),
    device_sequence: nextQmsFieldworkDeviceSequence(),
    client_timestamp: new Date().toISOString(),
    base_version: baseVersion,
  };
}

export function listChecklistExecutionGovernance(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<ChecklistExecutionGovernanceResponse>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-execution-governance`),
    { timeoutMs: 15_000, signal },
  );
}

export function updateChecklistExecutionGovernance(
  amoCode: string,
  auditId: string,
  itemId: string,
  payload: FieldworkMutationPayload,
) {
  return apiRequest<ChecklistExecutionGovernanceRow>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(itemId)}/execution-governance`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function mutateChecklistFieldwork(
  amoCode: string,
  auditId: string,
  item: Pick<ChecklistExecutionGovernanceRow, "checklist_item_id" | "entity_version">,
  payload: FieldworkMutationPayload,
  clientMutationId = newQmsFieldworkMutationId(),
) {
  const body = {
    ...fieldworkEnvelope(clientMutationId, item.entity_version),
    operation: "CHECKLIST_UPDATE" as const,
    canonical_response_status: payload.canonical_response_status,
    auditor_notes: payload.auditor_notes ?? null,
    evidence_references: payload.evidence_references ?? [],
    reason: payload.reason,
  };
  return apiRequest<FieldworkMutationResult>(
    qmsPath(
      amoCode,
      `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(item.checklist_item_id)}/fieldwork-mutations`,
    ),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": clientMutationId,
      },
      body: JSON.stringify(body),
      offline: {
        queueMutation: true,
        entityType: "qms-audit-checklist-item",
        entityId: item.checklist_item_id,
        idempotencyKey: clientMutationId,
      },
    },
  );
}

export function createAtomicChecklistFinding(
  amoCode: string,
  auditId: string,
  item: Pick<ChecklistExecutionGovernanceRow, "checklist_item_id" | "entity_version">,
  payload: AtomicFieldworkFindingPayload,
  clientMutationId = newQmsFieldworkMutationId(),
) {
  const body = {
    ...fieldworkEnvelope(clientMutationId, item.entity_version),
    operation: "CREATE_FINDING" as const,
    ...payload,
    safety_sensitive: payload.safety_sensitive ?? false,
    target_close_date: payload.target_close_date ?? null,
    auditor_notes: payload.auditor_notes ?? null,
    evidence_references: payload.evidence_references ?? [],
    reason: payload.reason,
  };
  return apiRequest<AtomicFieldworkFindingResult>(
    qmsPath(
      amoCode,
      `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(item.checklist_item_id)}/fieldwork-findings`,
    ),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": clientMutationId,
      },
      body: JSON.stringify(body),
      offline: {
        queueMutation: true,
        entityType: "qms-audit-checklist-item",
        entityId: item.checklist_item_id,
        idempotencyKey: clientMutationId,
      },
    },
  );
}
