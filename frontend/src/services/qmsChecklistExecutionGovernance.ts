import { apiRequest, qmsPath } from "./apiClient";
import { projectOfflineChecklistExecution, readAuditOfflinePack } from "./qmsAuditOfflinePack";
import { requireAuditContract } from "./qmsAuditWorkflowContract";

export type CanonicalChecklistResponse = "COMPLIANT" | "NONCOMPLIANT" | "OBSERVATION" | "NOT_APPLICABLE" | "NOT_VERIFIED";
export type FieldworkFindingResponse = "NONCOMPLIANT" | "OBSERVATION";
export type FieldworkFindingLevel = "LEVEL_1" | "LEVEL_2" | "LEVEL_3" | "LEVEL_4";
export type FieldworkFindingSeverity = "MINOR" | "MAJOR" | "CRITICAL";

export type AssessmentApplicability = "APPLICABLE" | "NOT_APPLICABLE" | "UNVERIFIED";
export type DocumentaryStatus = "DOCUMENTED" | "NOT_DOCUMENTED" | "PARTIALLY_DOCUMENTED" | "CONFLICT" | "NOT_EVIDENCED" | "UNVERIFIED";
export type ImplementationStatus = "OBJECTIVE_EVIDENCE_AVAILABLE" | "VERIFIED" | "NOT_VERIFIED" | "NOT_EVIDENCED" | "UNVERIFIED";
export type FieldVerificationStatus = "FIELD_VERIFICATION_REQUIRED" | "VERIFIED" | "NOT_VERIFIED" | "NOT_APPLICABLE" | "UNVERIFIED";

export type StructuredAIAnalysis = {
  conclusion?: string | null;
  evidence_ids: string[];
  missing_evidence: string[];
  conflicts: Array<Record<string, unknown> | string>;
  verification_required: string[];
  confidence_basis?: string | null;
};

export type ChecklistAssessmentState = {
  applicability: AssessmentApplicability;
  applicability_reason?: string | null;
  applicability_basis: Array<Record<string, unknown> | string>;
  documentary_status: DocumentaryStatus;
  implementation_status: ImplementationStatus;
  field_verification_status: FieldVerificationStatus;
  evidence_ids: string[];
  document_revision_ids: string[];
  regulation_refs: string[];
  procedure_refs: string[];
  conflicts: Array<Record<string, unknown> | string>;
  missing_evidence: string[];
  fieldwork_requirements: string[];
  ai_analysis?: StructuredAIAnalysis | null;
  human_decision?: CanonicalChecklistResponse | null;
  human_override_reason?: string | null;
};

export type EvidenceCandidate = {
  evidence_id: string;
  kind?: string | null;
  document_id?: string | null;
  document_code?: string | null;
  document_title?: string | null;
  revision_id: string;
  revision?: string | null;
  revision_status: string;
  effective_date?: string | null;
  section_id?: string | null;
  heading?: string | null;
  page_number?: number | null;
  snippet?: string | null;
  reader_url?: string | null;
  score?: number | null;
  reason?: string | null;
  retrieval_channels: string[];
  semantic_similarity?: number | null;
  current_approved: boolean;
  evidence_role?: string | null;
  authority_priority?: number | null;
  applicability: {
    status: AssessmentApplicability;
    reason: string;
    basis: Array<Record<string, unknown>>;
    missing_context?: string[];
    warnings?: Array<Record<string, unknown>>;
  };
};

export type EvidenceCandidateResponse = {
  checklist_item_id: string;
  query: string;
  evidence_context: string;
  retrieval_mode: string;
  authority_policy: Record<string, number>;
  applicability_context: AuditApplicabilityFact[];
  applicability_recommendation: {
    status: AssessmentApplicability;
    reason: string;
    basis: Array<Record<string, unknown>>;
  };
  documentary_recommendation: DocumentaryStatus;
  conflicts: Array<Record<string, unknown>>;
  items: EvidenceCandidate[];
  limitations: string[];
};

export type GovernedApplicabilityRule = {
  id: string;
  manual_id: string;
  revision_id?: string | null;
  rule_type: "INCLUDE" | "EXCLUDE" | "WARNING";
  target_type: string;
  target_id?: string | null;
  target_value?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  status: string;
  source: string;
  criteria: Record<string, unknown>;
  document_code: string;
  document_title: string;
  current_revision_id: string;
  current_revision: string;
  selected: boolean;
};

export type AuditApplicabilityFact = {
  id: string;
  applicability_rule_id: string;
  source_manual_id: string;
  source_revision_id?: string | null;
  rule_type: "INCLUDE" | "EXCLUDE" | "WARNING";
  target_type: string;
  target_id?: string | null;
  target_value?: string | null;
  source: string;
  criteria: Record<string, unknown>;
  reason: string;
  created_by_user_id?: string | null;
  created_at: string;
};

export type AuditApplicabilityContextResponse = {
  items: AuditApplicabilityFact[];
  available_rules: GovernedApplicabilityRule[];
};

export type ChecklistExecutionGovernanceRow = {
  checklist_item_id: string;
  audit_id: string;
  section?: string | null;
  checklist_ref?: string | null;
  requirement_ref?: string | null;
  prompt: string;
  legacy_response_status: string;
  canonical_response_status: CanonicalChecklistResponse;
  response_value?: string | null;
  objective_evidence?: string | null;
  finding_id?: string | null;
  auditor_notes?: string | null;
  auditee_comments?: string | null;
  sampled_item_information?: string | null;
  applicability?: string | null;
  evidence_references: Array<Record<string, unknown> | string>;
  assessment: ChecklistAssessmentState;
  governance_id?: string | null;
  entity_version: number;
  answered_by_user_id?: string | null;
  answered_at?: string | null;
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
  response_value?: string | null;
  auditor_notes?: string | null;
  sampled_item_information?: string | null;
  evidence_references?: Array<Record<string, unknown> | string>;
  assessment?: ChecklistAssessmentState | null;
  reason: string;
};

export type AtomicFieldworkFindingPayload = {
  canonical_response_status: FieldworkFindingResponse;
  response_value?: string | null;
  severity: FieldworkFindingSeverity;
  level: FieldworkFindingLevel;
  requirement_ref?: string | null;
  description: string;
  objective_evidence?: string | null;
  safety_sensitive?: boolean;
  target_close_date?: string | null;
  auditor_notes?: string | null;
  sampled_item_information?: string | null;
  evidence_references?: Array<Record<string, unknown> | string>;
  assessment?: ChecklistAssessmentState | null;
  reason: string;
};

const FIELDWORK_DEVICE_KEY = "amo:qms:fieldwork-device-id";
const FIELDWORK_SEQUENCE_KEY = "amo:qms:fieldwork-device-sequence";
const FIELDWORK_CACHE_TTL_MS = 30_000;
const FIELDWORK_STALE_OFFLINE_MS = 24 * 60 * 60_000;

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

export async function listChecklistExecutionGovernance(amoCode: string, auditId: string, signal?: AbortSignal) {
  const readOffline = async () => {
    const pack = await readAuditOfflinePack(amoCode, auditId);
    return pack ? requireAuditContract(projectOfflineChecklistExecution(pack) as ChecklistExecutionGovernanceResponse, "checklist") : null;
  };
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    const offline = await readOffline();
    if (offline) return offline;
  }
  try {
    return requireAuditContract(await apiRequest<ChecklistExecutionGovernanceResponse>(
      qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/checklist-execution-governance`),
      {
        timeoutMs: 15_000,
        cacheTtlMs: FIELDWORK_CACHE_TTL_MS,
        staleWhileOfflineMs: FIELDWORK_STALE_OFFLINE_MS,
        signal,
      },
    ), "checklist");
  } catch (error) {
    const message = error instanceof Error ? error.message.toLowerCase() : "";
    if (!message.includes("offline") && !message.includes("could not be reached") && !message.includes("cached copy")) throw error;
    const offline = await readOffline();
    if (offline) return offline;
    throw error;
  }
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
    response_value: payload.response_value ?? null,
    auditor_notes: payload.auditor_notes ?? null,
    sampled_item_information: payload.sampled_item_information ?? null,
    evidence_references: payload.evidence_references ?? [],
    assessment: payload.assessment ?? null,
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
        requireDurable: true,
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
    sampled_item_information: payload.sampled_item_information ?? null,
    evidence_references: payload.evidence_references ?? [],
    assessment: payload.assessment ?? null,
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
        requireDurable: true,
      },
    },
  );
}


export function getChecklistEvidenceCandidates(
  amoCode: string,
  auditId: string,
  itemId: string,
  signal?: AbortSignal,
) {
  return apiRequest<EvidenceCandidateResponse>(
    qmsPath(
      amoCode,
      `/audits/${encodeURIComponent(auditId)}/checklist-items/${encodeURIComponent(itemId)}/evidence-candidates`,
    ),
    { timeoutMs: 20_000, cacheTtlMs: 15_000, signal },
  ).then((data) => requireAuditContract(data, "candidates"));
}

export function getAuditApplicabilityContext(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditApplicabilityContextResponse>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/applicability-context`),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function addAuditApplicabilityFact(
  amoCode: string,
  auditId: string,
  applicabilityRuleId: string,
  reason: string,
) {
  return apiRequest<AuditApplicabilityFact>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/applicability-context`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ applicability_rule_id: applicabilityRuleId, reason }),
    },
  );
}

export function removeAuditApplicabilityFact(amoCode: string, auditId: string, factId: string) {
  return apiRequest<void>(
    qmsPath(
      amoCode,
      `/audits/${encodeURIComponent(auditId)}/applicability-context/${encodeURIComponent(factId)}`,
    ),
    { method: "DELETE" },
  );
}
