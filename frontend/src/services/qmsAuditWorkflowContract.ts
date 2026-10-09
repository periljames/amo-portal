import { z } from "zod";

const stageId = z.enum(["setup", "prepare", "live", "closing", "follow-up", "archive"]);
const readiness = z.object({ ready: z.boolean(), blockers: z.array(z.object({ type: z.string(), reason: z.string() }).passthrough()) }).passthrough();
const report = z.object({ id: z.string(), audit_id: z.string(), revision_no: z.number().int().positive(), status: z.enum(["DRAFT", "INTERNAL_REVIEW", "APPROVED", "ISSUED", "SUPERSEDED", "CANCELLED"]), sha256: z.string(), filename: z.string() }).passthrough();
const row = z.object({ id: z.string().min(1) }).passthrough();
const strings = z.array(z.string());
const refs = z.array(z.union([z.string(), z.record(z.unknown())]));
const response = z.enum(["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"]);
const assessment = z.object({
  applicability: z.enum(["APPLICABLE", "NOT_APPLICABLE", "UNVERIFIED"]),
  applicability_reason: z.string().nullable().optional(), applicability_basis: refs,
  documentary_status: z.string(), implementation_status: z.string(), field_verification_status: z.string(),
  evidence_ids: strings, document_revision_ids: strings, regulation_refs: strings, procedure_refs: strings,
  conflicts: refs, missing_evidence: strings, fieldwork_requirements: strings,
  ai_analysis: z.object({ evidence_ids: strings, missing_evidence: strings, conflicts: refs, verification_required: strings }).passthrough().nullable().optional(),
}).passthrough();
const checklistSource = z.object({
  prompt: z.string(), response_type: z.string(),
  response_options: z.array(z.object({ value: z.string(), label: z.string(), canonical_status: response })).optional(),
  evidence_types: strings.optional(), evidence_required_when: z.array(response).optional(), notes_required_when: z.array(response).optional(),
}).passthrough();
const retentionPolicy = row.extend({ retention_class: z.string(), governing_basis: z.string(), retention_start_event: z.enum(["EXECUTION_CLOSED", "FOLLOW_UP_COMPLETE"]), indefinite: z.boolean(), disposition_mode: z.enum(["PRESERVE_METADATA_DELETE_PACKAGE", "TRANSFER_PACKAGE", "NO_DISPOSITION"]) });
const contracts = {
  occurrence: row.extend({ title: z.string(), audit_ref: z.string(), status: z.enum(["PLANNED", "IN_PROGRESS", "CAP_OPEN", "CLOSED"]), supporting_auditor_user_ids: strings.nullable().optional(), external_auditees: z.array(z.unknown()).nullable().optional() }),
  findings: z.array(row.extend({ audit_id: z.string().optional(), description: z.string(), severity: z.string(), level: z.string() })),
  findingReleases: z.object({ items: z.array(z.object({ finding_id: z.string(), action: z.enum(["RELEASED", "WITHDRAWN"]), include_objective_evidence: z.boolean(), released_evidence_refs: refs }).passthrough()) }),
  evidence: z.object({ items: z.array(row.extend({ audit_id: z.string(), filename: z.string(), source_type: z.string(), size_bytes: z.number(), sha256: z.string() })) }),
  checklist: z.object({ items: z.array(z.object({ checklist_item_id: z.string(), audit_id: z.string(), prompt: z.string(), canonical_response_status: response, entity_version: z.number().int().nonnegative(), evidence_references: refs, assessment, events: z.array(z.unknown()) }).passthrough()), canonical_response_values: z.array(response) }),
  bindings: z.object({ items: z.array(row.extend({ audit_id: z.string(), template_code: z.string(), revision_no: z.number(), content_sha256: z.string(), item_snapshot: z.array(checklistSource), instantiated_item_ids: strings }).refine((binding) => binding.item_snapshot.length === binding.instantiated_item_ids.length)) }),
  candidates: z.object({ items: z.array(z.object({ evidence_id: z.string(), revision_id: z.string(), revision_status: z.string(), retrieval_channels: strings, applicability: z.object({ status: z.string(), reason: z.string(), basis: z.array(z.record(z.unknown())) }).passthrough() }).passthrough()), limitations: strings, conflicts: z.array(z.record(z.unknown())), applicability_recommendation: z.object({ status: z.string(), reason: z.string(), basis: z.array(z.record(z.unknown())) }).passthrough() }).passthrough(),
  externalDrafts: z.object({ items: z.array(row.extend({ status: z.enum(["CREATED", "SUBMITTED", "RETURNED", "PROMOTED", "WITHDRAWN"]), description: z.string(), evidence_references: refs, events: z.array(row) })) }),
  meetings: z.object({ items: z.array(row.extend({ meeting_type: z.string(), status: z.string(), scheduled_start: z.string() })) }),
  narrative: z.object({ management_summary: z.string().nullable(), conclusion: z.string().nullable(), positive_practices: z.string().nullable() }),
  presence: z.object({ items: z.array(row.extend({ actor_type: z.enum(["INTERNAL_USER", "EXTERNAL_AUDITOR", "AUDITEE_GUEST"]), display_name: z.string() })) }),
  session: z.object({
    audit_id: z.string(), current_stage_id: stageId, current_stage_label: z.string(),
    stages: z.array(z.object({ id: stageId, complete: z.boolean(), active: z.boolean() }).passthrough()).length(6).refine((stages) => new Set(stages.map((stage) => stage.id)).size === 6),
    preparation_issued: z.boolean(), execution_status: z.string(), follow_up_status: z.string(), archive_count: z.number(),
    fieldwork_access: z.object({ ready: z.boolean(), blocker: z.string().nullable() }).optional(),
  }).passthrough(),
  closure: z.object({ audit_id: z.string(), execution_status: z.enum(["OPEN", "CLOSED"]), follow_up_status: z.enum(["OPEN", "COMPLETE"]), execution_readiness: readiness, follow_up_readiness: readiness, events: z.array(z.unknown()) }).passthrough(),
  report,
  reports: z.object({ items: z.array(report) }).passthrough(),
  composition: z.object({ audit: row.extend({ audit_ref: z.string(), title: z.string(), actual_end: z.string().nullable() }), checklist_counts: z.record(z.number().int().nonnegative()), findings_count: z.number(), cars_count: z.number(), artifacts: z.array(row.extend({ filename: z.string(), sha256: z.string() })) }).passthrough(),
  outputPolicy: z.object({ configured: z.boolean(), current: row.extend({ artifact_policy: z.enum(["NONE", "REPORT_ONLY", "APPROVAL_LETTER", "CERTIFICATE", "ATTESTATION"]) }).nullable() }),
  signatures: z.object({ items: z.array(row.extend({ report_revision_id: z.string(), artifact_sha256: z.string(), method: z.string() })) }),
  acknowledgements: z.object({ items: z.array(row.extend({ report_revision_id: z.string(), report_sha256: z.string(), acknowledgement_status: z.string() })) }),
  passkeys: z.object({ items: z.array(row.extend({ is_active: z.boolean(), transports: strings })) }),
  assuranceArtifacts: z.object({ items: z.array(row.extend({ source_report_revision_id: z.string(), signature_evidence_id: z.string(), filename: z.string() })) }),
  cars: z.object({ items: z.array(row.extend({ car_number: z.string(), title: z.string(), status: z.string(), priority: z.string() })), total: z.number().int().nonnegative(), limit: z.number().int().positive(), offset: z.number().int().nonnegative() }).passthrough(),
  controlLoop: z.object({ initialized: z.boolean(), car: row.extend({ car_number: z.string(), status: z.string() }), profile: row.nullable(), milestones: z.array(row.extend({ milestone_key: z.string(), status: z.string() })), dependencies: z.array(row.extend({ status: z.string() })), deadline_changes: z.array(row), legacy_extension_history: z.array(z.unknown()), events: z.array(row), health: z.object({}).passthrough(), closure_readiness: z.object({ ready: z.boolean(), blockers: z.array(z.object({ code: z.string(), message: z.string() }).passthrough()) }) }).passthrough(),
  archive: z.object({ policy: z.object({ configured: z.boolean(), current: retentionPolicy.nullable().optional() }), manifest: row.extend({ manifest_version: z.number(), items: z.array(row.extend({ item_type: z.string() })), package_available: z.boolean().optional() }).nullable().optional(), active_holds: z.array(z.object({ hold_key: z.string(), reason: z.string(), governing_basis: z.string() }).passthrough()), retention_due: z.boolean(), archive_readiness: readiness.optional(), disposition_review_valid: z.boolean().optional(), disposition: z.object({ event_type: z.enum(["APPROVED", "REJECTED", "EXECUTED"]) }).passthrough().nullable().optional() }).passthrough(),
};

export function requireAuditContract<T>(data: T, kind: keyof typeof contracts): T {
  const result = contracts[kind].safeParse(data);
  if (!result.success) {
    console.warn(`[QMS audit] Invalid ${kind} response fields`, result.error.issues.map((issue) => ({ path: issue.path.join("."), code: issue.code })));
    throw new Error("Audit workflow data could not be verified. Retry to load the current saved record.");
  }
  return data;
}
