import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const target = path.join(root, "src/services/reliability.ts");
let text = fs.readFileSync(target, "utf8");

const oldUnion = 'export type ReliabilityEventType = "DEFECT" | "REMOVAL" | "INSTALLATION" | "OCTM" | "ECTM" | "FRACAS" | "OTHER";';
const newUnion = `export type ReliabilityEventType =
  | "DEFECT" | "REPEAT_DEFECT" | "PILOT_REPORT" | "CABIN_REPORT"
  | "TECHNICAL_DELAY" | "TECHNICAL_CANCELLATION" | "RETURN_TO_GATE"
  | "AIR_TURNBACK" | "DIVERSION" | "IN_FLIGHT_SHUTDOWN" | "ABORTED_TAKEOFF"
  | "MEL_DEFERRAL" | "CDL_DEFERRAL" | "UNSCHEDULED_REMOVAL" | "SCHEDULED_REMOVAL"
  | "REMOVAL" | "INSTALLATION" | "SHOP_FINDING" | "NO_FAULT_FOUND"
  | "OCTM" | "ECTM" | "EHM_ALERT" | "FRACAS" | "MAINTENANCE_ERROR"
  | "SUPPLIER_ESCAPE" | "SAFETY_EVENT" | "OTHER";`;
if (text.includes(oldUnion)) text = text.replace(oldUnion, newUnion);

const eventAnchor = `  source_system?: string | null;\n  description?: string | null;`;
const eventFields = `  source_system?: string | null;
  source_record_id?: string | null;
  source_payload_hash?: string | null;
  validation_status?: string;
  validation_errors?: Array<Record<string, unknown>>;
  provenance_json?: Record<string, unknown>;
  operation_stage?: string | null;
  flight_number?: string | null;
  origin_station?: string | null;
  destination_station?: string | null;
  delay_minutes?: number | null;
  mel_reference?: string | null;
  cdl_reference?: string | null;
  deferral_expires_at?: string | null;
  part_number?: string | null;
  component_serial_number?: string | null;
  confirmed_failure?: boolean | null;
  repeat_key?: string | null;
  description?: string | null;`;
if (text.includes(eventAnchor)) text = text.replace(eventAnchor, eventFields);

const marker = "// COMPLETE_RELIABILITY_DOMAIN_CLIENT";
if (!text.includes(marker)) {
  text += `

${marker}
export type ReliabilityCapabilitySnapshot = { capabilities: string[]; superuser: boolean };
export type ReliabilitySource = {
  id: string; amo_id: string; code: string; name: string; source_type: string;
  status: string; transport: string; mapping_version: string;
  configuration_json: Record<string, unknown>; poll_interval_minutes?: number | null;
  next_poll_at?: string | null; last_received_at?: string | null;
  last_success_at?: string | null; last_failure_at?: string | null;
  last_cursor?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityIngestionBatch = {
  id: string; amo_id: string; source_id: string; status: string; content_hash: string;
  record_count: number; valid_count: number; duplicate_count: number; invalid_count: number;
  metadata_json: Record<string, unknown>; error_summary?: string | null;
  received_at: string; completed_at?: string | null;
};
export type ReliabilityIngestionResult = {
  batch: ReliabilityIngestionBatch; created_event_ids: number[];
  duplicate_external_ids: string[]; rejected_records: Array<Record<string, unknown>>;
};
export type ReliabilityDataQualityIssue = {
  id: string; amo_id: string; source_id?: string | null; batch_id?: string | null;
  record_id?: string | null; issue_code: string; severity: string; status: string;
  message: string; details_json: Record<string, unknown>; resolution?: string | null;
  resolved_at?: string | null; created_at: string;
};
export type OccurrenceProvenance = {
  event_id: number; source?: ReliabilitySource | null; batch?: ReliabilityIngestionBatch | null;
  external_id?: string | null; payload_hash?: string | null; validation_status?: string | null;
  validation_errors: unknown[]; raw_payload?: Record<string, unknown> | null;
  interruption?: Record<string, unknown> | null;
};
export type FracasLifecycle = {
  id: string; amo_id: string; fracas_case_id: number; stage: string;
  triage_disposition?: string | null; containment_required: boolean;
  containment_complete: boolean; problem_statement?: string | null;
  root_cause_method?: string | null; root_cause_json: Record<string, unknown>;
  risk_assessment_json: Record<string, unknown>; effectiveness_due_date?: string | null;
  reopened_count: number; owner_user_id?: string | null; stage_entered_at: string;
  created_at: string; updated_at: string;
};
export type FracasEvidence = {
  id: string; lifecycle_id: string; evidence_type: string; reference_type?: string | null;
  reference_id?: string | null; reference_url?: string | null; title: string;
  description?: string | null; source_hash: string; metadata_json: Record<string, unknown>;
  captured_at: string; captured_by_user_id?: string | null;
};
export type FracasStageEvent = {
  id: string; lifecycle_id: string; from_stage?: string | null; to_stage: string;
  decision: string; rationale: string; payload_json: Record<string, unknown>;
  previous_hash?: string | null; event_hash: string; actor_user_id?: string | null;
  created_at: string;
};
export type EffectivenessReview = {
  id: string; lifecycle_id: string; review_date: string; metric_code?: string | null;
  baseline_value?: string | null; current_value?: string | null; acceptance_criteria: string;
  outcome: string; evidence_json: Array<Record<string, unknown>>; notes?: string | null;
  reviewer_user_id?: string | null; approved_by_user_id?: string | null;
  approved_at?: string | null; created_at: string;
};
export type ReliabilityProgramme = {
  id: string; amo_id: string; code: string; name: string; description?: string | null;
  status: string; owner_user_id?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityProgrammeVersion = {
  id: string; amo_id: string; programme_id: string; revision: string; status: string;
  effective_from?: string | null; effective_to?: string | null; change_summary: string;
  regulatory_profiles: string[]; scope_json: Record<string, unknown>;
  data_sources_json: Array<Record<string, unknown>>; reporting_json: Record<string, unknown>;
  responsibility_matrix_json: Record<string, unknown>; approval_json: Record<string, unknown>;
  authority_required: boolean; approved_by_user_id?: string | null;
  approved_at?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityMetricDefinition = {
  id: string; programme_version_id: string; code: string; name: string;
  description?: string | null; scope_type: string; method: string;
  numerator_event_types: string[]; denominator_type: string; multiplier: string;
  window_days: number; schedule_interval_minutes: number; minimum_exposure: string;
  direction: string; formula_version: string; active: boolean;
  next_run_at?: string | null; last_run_at?: string | null;
};
export type ReliabilityThresholdVersion = {
  id: string; metric_definition_id: string; version: string; status: string;
  caution_value?: string | null; alert_value?: string | null;
  lower_caution_value?: string | null; lower_alert_value?: string | null;
  minimum_exposure?: string | null; rationale: string; effective_from?: string | null;
  effective_to?: string | null; approved_by_user_id?: string | null; approved_at?: string | null;
};
export type ReliabilityCalculationRun = {
  id: string; metric_definition_id: string; scope_type: string; scope_id: string;
  period_start: string; period_end: string; numerator?: string | null;
  denominator?: string | null; value?: string | null; confidence_lower?: string | null;
  confidence_upper?: string | null; sample_size: number; small_fleet: boolean;
  status: string; formula_version: string; source_cutoff_at: string;
  source_lineage_json: Record<string, unknown>; result_hash: string;
  scheduled: boolean; created_at: string;
};
export type ReliabilityAnalyticsRow = {
  scope_type: string; scope_id: string; label: string; events: number; exposure: string;
  rate?: string | null; confidence_lower?: string | null; confidence_upper?: string | null;
  small_fleet: boolean; status: string; details: Record<string, unknown>;
};
export type ReliabilityAnalytics = {
  generated_at: string; period_start: string; period_end: string; scope_type: string;
  denominator_type: string; multiplier: string; rows: ReliabilityAnalyticsRow[];
};
export type ReliabilityMeeting = {
  id: string; programme_version_id?: string | null; meeting_type: string; title: string;
  scheduled_at: string; status: string; data_cutoff_at?: string | null;
  agenda_json: Array<Record<string, unknown>>; attendees_json: Array<Record<string, unknown>>;
  quorum_json: Record<string, unknown>; minutes?: string | null;
  chaired_by_user_id?: string | null; approved_by_user_id?: string | null;
  approved_at?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityMeetingDecision = {
  id: string; meeting_id: string; decision_type: string; title: string; decision: string;
  rationale: string; dissent?: string | null; linked_entity_type?: string | null;
  linked_entity_id?: string | null; owner_user_id?: string | null; due_date?: string | null;
  status: string; created_at: string;
};
export type ReliabilityChangeProposal = {
  id: string; programme_version_id?: string | null; source_type: string; source_id: string;
  proposal_type: string; title: string; problem_statement: string;
  proposed_change_json: Record<string, unknown>; impact_assessment_json: Record<string, unknown>;
  simulation_json: Record<string, unknown>; status: string; approval_json: Record<string, unknown>;
  effective_from?: string | null; effectiveness_due_date?: string | null;
  owner_user_id?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityHandoff = {
  id: string; source_type: string; source_id: string; target_module: string;
  target_route?: string | null; target_record_type?: string | null; target_record_id?: string | null;
  task_id?: string | null; payload_json: Record<string, unknown>; status: string;
  owner_user_id?: string | null; sent_at?: string | null; acknowledged_at?: string | null;
  completed_at?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityAuthoritySubmission = {
  id: string; programme_version_id?: string | null; change_proposal_id?: string | null;
  meeting_id?: string | null; authority_profile: string; submission_type: string; status: string;
  external_reference?: string | null; package_manifest_json: Record<string, unknown>;
  response_json: Record<string, unknown>; submitted_by_user_id?: string | null;
  submitted_at?: string | null; decision_at?: string | null; created_at: string; updated_at: string;
};
export type ReliabilityAiReview = {
  id: string; review_type: string; entity_type: string; entity_id: string;
  model_id: string; model_version: string; prompt_hash: string;
  input_snapshot_json: Record<string, unknown>; citations_json: Array<Record<string, unknown>>;
  output_json: Record<string, unknown>; confidence?: string | null; advisory_only: boolean;
  status: string; review_notes?: string | null; created_by_user_id?: string | null;
  reviewed_by_user_id?: string | null; reviewed_at?: string | null; created_at: string;
};
export type ReliabilityAuditEvent = {
  id: string; entity_type: string; entity_id: string; action: string;
  payload_json: Record<string, unknown>; actor_user_id?: string | null;
  previous_hash?: string | null; event_hash: string; created_at: string;
};
export type ReliabilityComplianceCheck = {
  code: string; title: string; status: "GREEN" | "AMBER" | "RED" | "UNKNOWN";
  detail: string; count?: number | null; route?: string | null;
};
export type ReliabilityCompliance = {
  generated_at: string; overall_status: "GREEN" | "AMBER" | "RED" | "UNKNOWN";
  regulatory_profiles: string[]; checks: ReliabilityComplianceCheck[]; disclaimer: string;
};
export type ReliabilityBootstrapResult = {
  programme_id: string; programme_version_id: string; source_ids: string[];
  metric_ids: string[]; created: Record<string, number>;
};

function reliabilityMutation<T>(path: string, method: "POST" | "PUT", payload?: unknown): Promise<T> {
  return apiRequest(path, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cacheTtlMs: 0,
  });
}

export const getReliabilityCapabilities = (): Promise<ReliabilityCapabilitySnapshot> =>
  apiRequest("/reliability/capabilities", { cacheTtlMs: 15_000 });
export const bootstrapReliability = (): Promise<ReliabilityBootstrapResult> =>
  reliabilityMutation("/reliability/bootstrap", "POST");
export const listReliabilitySources = (): Promise<ReliabilitySource[]> =>
  apiRequest("/reliability/sources", { cacheTtlMs: 15_000, persistCache: true });
export const createReliabilitySource = (payload: Record<string, unknown>): Promise<ReliabilitySource> =>
  reliabilityMutation("/reliability/sources", "POST", payload);
export const ingestReliabilitySource = (sourceId: string, records: Array<Record<string, unknown>>, metadata_json: Record<string, unknown> = {}): Promise<ReliabilityIngestionResult> =>
  reliabilityMutation(\`/reliability/sources/\${encodeURIComponent(sourceId)}/ingest\`, "POST", { records, metadata_json });
export const harvestInternalReliabilitySources = (): Promise<ReliabilityIngestionResult[]> =>
  reliabilityMutation("/reliability/sources/harvest-internal", "POST");
export const listReliabilityIngestionBatches = (sourceId?: string): Promise<ReliabilityIngestionBatch[]> =>
  apiRequest(\`/reliability/ingestion-batches\${queryString({ source_id: sourceId, limit: 200 })}\`, { cacheTtlMs: 10_000 });
export const listReliabilityDataQualityIssues = (status?: string, sourceId?: string): Promise<ReliabilityDataQualityIssue[]> =>
  apiRequest(\`/reliability/data-quality/issues\${queryString({ status, source_id: sourceId, limit: 500 })}\`, { cacheTtlMs: 10_000 });
export const resolveReliabilityDataQualityIssue = (issueId: string, resolution: string, status = "RESOLVED"): Promise<ReliabilityDataQualityIssue> =>
  reliabilityMutation(\`/reliability/data-quality/issues/\${encodeURIComponent(issueId)}/resolve\`, "POST", { resolution, status });
export const getOccurrenceProvenance = (eventId: number): Promise<OccurrenceProvenance> =>
  apiRequest(\`/reliability/events/\${eventId}/provenance\`, { cacheTtlMs: 20_000 });

export const getFracasLifecycle = (caseId: number): Promise<FracasLifecycle> =>
  apiRequest(\`/reliability/fracas/cases/\${caseId}/lifecycle\`, { cacheTtlMs: 5_000 });
export const updateFracasLifecycle = (caseId: number, payload: Record<string, unknown>): Promise<FracasLifecycle> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/lifecycle\`, "PUT", payload);
export const transitionFracasLifecycle = (caseId: number, payload: Record<string, unknown>): Promise<FracasLifecycle> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/transition\`, "POST", payload);
export const listFracasEvidence = (caseId: number): Promise<FracasEvidence[]> =>
  apiRequest(\`/reliability/fracas/cases/\${caseId}/evidence\`, { cacheTtlMs: 5_000 });
export const addFracasEvidence = (caseId: number, payload: Record<string, unknown>): Promise<FracasEvidence> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/evidence\`, "POST", payload);
export const listFracasStageEvents = (caseId: number): Promise<FracasStageEvent[]> =>
  apiRequest(\`/reliability/fracas/cases/\${caseId}/stage-events\`, { cacheTtlMs: 5_000 });
export const listEffectivenessReviews = (caseId: number): Promise<EffectivenessReview[]> =>
  apiRequest(\`/reliability/fracas/cases/\${caseId}/effectiveness\`, { cacheTtlMs: 5_000 });
export const addEffectivenessReview = (caseId: number, payload: Record<string, unknown>, approve = false): Promise<EffectivenessReview> =>
  reliabilityMutation(\`/reliability/fracas/cases/\${caseId}/effectiveness?approve=\${approve}\`, "POST", payload);

export const listReliabilityProgrammes = (): Promise<ReliabilityProgramme[]> =>
  apiRequest("/reliability/programmes", { cacheTtlMs: 15_000 });
export const createReliabilityProgramme = (payload: Record<string, unknown>): Promise<ReliabilityProgramme> =>
  reliabilityMutation("/reliability/programmes", "POST", payload);
export const listReliabilityProgrammeVersions = (programmeId?: string): Promise<ReliabilityProgrammeVersion[]> =>
  apiRequest(\`/reliability/programme-versions\${queryString({ programme_id: programmeId })}\`, { cacheTtlMs: 15_000 });
export const createReliabilityProgrammeVersion = (programmeId: string, payload: Record<string, unknown>): Promise<ReliabilityProgrammeVersion> =>
  reliabilityMutation(\`/reliability/programmes/\${encodeURIComponent(programmeId)}/versions\`, "POST", payload);
export const transitionReliabilityProgrammeVersion = (versionId: string, to_status: string, rationale: string): Promise<ReliabilityProgrammeVersion> =>
  reliabilityMutation(\`/reliability/programme-versions/\${encodeURIComponent(versionId)}/transition\`, "POST", { to_status, rationale });
export const listReliabilityMetricDefinitions = (versionId?: string): Promise<ReliabilityMetricDefinition[]> =>
  apiRequest(\`/reliability/metric-definitions\${queryString({ programme_version_id: versionId })}\`, { cacheTtlMs: 15_000 });
export const createReliabilityMetricDefinition = (versionId: string, payload: Record<string, unknown>): Promise<ReliabilityMetricDefinition> =>
  reliabilityMutation(\`/reliability/programme-versions/\${encodeURIComponent(versionId)}/metrics\`, "POST", payload);
export const listReliabilityThresholdVersions = (metricId?: string): Promise<ReliabilityThresholdVersion[]> =>
  apiRequest(\`/reliability/threshold-versions\${queryString({ metric_id: metricId })}\`, { cacheTtlMs: 15_000 });
export const createReliabilityThresholdVersion = (metricId: string, payload: Record<string, unknown>): Promise<ReliabilityThresholdVersion> =>
  reliabilityMutation(\`/reliability/metric-definitions/\${encodeURIComponent(metricId)}/thresholds\`, "POST", payload);
export const transitionReliabilityThresholdVersion = (thresholdId: string, to_status: string, rationale: string): Promise<ReliabilityThresholdVersion> =>
  reliabilityMutation(\`/reliability/threshold-versions/\${encodeURIComponent(thresholdId)}/transition\`, "POST", { to_status, rationale });
export const executeReliabilityCalculation = (payload: Record<string, unknown>): Promise<ReliabilityCalculationRun> =>
  reliabilityMutation("/reliability/calculation-runs/execute", "POST", payload);
export const runDueReliabilityCalculations = (): Promise<ReliabilityCalculationRun[]> =>
  reliabilityMutation("/reliability/calculation-runs/run-due", "POST");
export const listReliabilityCalculationRuns = (metricId?: string, scopeType?: string): Promise<ReliabilityCalculationRun[]> =>
  apiRequest(\`/reliability/calculation-runs\${queryString({ metric_id: metricId, scope_type: scopeType, limit: 500 })}\`, { cacheTtlMs: 10_000 });
export const getReliabilityAnalytics = (params: { scopeType: string; periodStart: string; periodEnd: string; denominatorType?: string; multiplier?: number; eventTypes?: string[] }): Promise<ReliabilityAnalytics> => {
  const search = new URLSearchParams({
    scope_type: params.scopeType,
    period_start: params.periodStart,
    period_end: params.periodEnd,
    denominator_type: params.denominatorType || "FH",
    multiplier: String(params.multiplier || 100),
  });
  for (const eventType of params.eventTypes || []) search.append("event_types", eventType);
  return apiRequest(\`/reliability/analytics?\${search.toString()}\`, { cacheTtlMs: 20_000 });
};

export const listReliabilityMeetings = (): Promise<ReliabilityMeeting[]> =>
  apiRequest("/reliability/meetings", { cacheTtlMs: 10_000 });
export const createReliabilityMeeting = (payload: Record<string, unknown>): Promise<ReliabilityMeeting> =>
  reliabilityMutation("/reliability/meetings", "POST", payload);
export const transitionReliabilityMeeting = (meetingId: string, payload: Record<string, unknown>): Promise<ReliabilityMeeting> =>
  reliabilityMutation(\`/reliability/meetings/\${encodeURIComponent(meetingId)}/transition\`, "POST", payload);
export const listReliabilityMeetingDecisions = (meetingId: string): Promise<ReliabilityMeetingDecision[]> =>
  apiRequest(\`/reliability/meetings/\${encodeURIComponent(meetingId)}/decisions\`, { cacheTtlMs: 10_000 });
export const createReliabilityMeetingDecision = (meetingId: string, payload: Record<string, unknown>): Promise<ReliabilityMeetingDecision> =>
  reliabilityMutation(\`/reliability/meetings/\${encodeURIComponent(meetingId)}/decisions\`, "POST", payload);

export const listReliabilityChanges = (status?: string): Promise<ReliabilityChangeProposal[]> =>
  apiRequest(\`/reliability/changes\${queryString({ status })}\`, { cacheTtlMs: 10_000 });
export const createReliabilityChange = (payload: Record<string, unknown>): Promise<ReliabilityChangeProposal> =>
  reliabilityMutation("/reliability/changes", "POST", payload);
export const simulateReliabilityChange = (changeId: string, payload: Record<string, unknown>): Promise<ReliabilityChangeProposal> =>
  reliabilityMutation(\`/reliability/changes/\${encodeURIComponent(changeId)}/simulate\`, "POST", payload);
export const transitionReliabilityChange = (changeId: string, payload: Record<string, unknown>): Promise<ReliabilityChangeProposal> =>
  reliabilityMutation(\`/reliability/changes/\${encodeURIComponent(changeId)}/transition\`, "POST", payload);

export const listReliabilityHandoffs = (targetModule?: string, status?: string): Promise<ReliabilityHandoff[]> =>
  apiRequest(\`/reliability/handoffs\${queryString({ target_module: targetModule, status })}\`, { cacheTtlMs: 10_000 });
export const createReliabilityHandoff = (payload: Record<string, unknown>): Promise<ReliabilityHandoff> =>
  reliabilityMutation("/reliability/handoffs", "POST", payload);
export const transitionReliabilityHandoff = (handoffId: string, payload: Record<string, unknown>): Promise<ReliabilityHandoff> =>
  reliabilityMutation(\`/reliability/handoffs/\${encodeURIComponent(handoffId)}/transition\`, "POST", payload);

export const listReliabilityAuthoritySubmissions = (): Promise<ReliabilityAuthoritySubmission[]> =>
  apiRequest("/reliability/authority-submissions", { cacheTtlMs: 10_000 });
export const createReliabilityAuthoritySubmission = (payload: Record<string, unknown>): Promise<ReliabilityAuthoritySubmission> =>
  reliabilityMutation("/reliability/authority-submissions", "POST", payload);
export const transitionReliabilityAuthoritySubmission = (submissionId: string, payload: Record<string, unknown>): Promise<ReliabilityAuthoritySubmission> =>
  reliabilityMutation(\`/reliability/authority-submissions/\${encodeURIComponent(submissionId)}/transition\`, "POST", payload);

export const listReliabilityAiReviews = (entityType?: string, entityId?: string): Promise<ReliabilityAiReview[]> =>
  apiRequest(\`/reliability/ai-reviews\${queryString({ entity_type: entityType, entity_id: entityId })}\`, { cacheTtlMs: 10_000 });
export const createReliabilityAiReview = (payload: Record<string, unknown>): Promise<ReliabilityAiReview> =>
  reliabilityMutation("/reliability/ai-reviews", "POST", payload);
export const decideReliabilityAiReview = (reviewId: string, decision: string, review_notes: string): Promise<ReliabilityAiReview> =>
  reliabilityMutation(\`/reliability/ai-reviews/\${encodeURIComponent(reviewId)}/decision\`, "POST", { decision, review_notes });
export const listReliabilityAuditEvents = (entityType?: string, entityId?: string): Promise<ReliabilityAuditEvent[]> =>
  apiRequest(\`/reliability/audit-events\${queryString({ entity_type: entityType, entity_id: entityId, limit: 500 })}\`, { cacheTtlMs: 10_000 });
export const getReliabilityCompliance = (): Promise<ReliabilityCompliance> =>
  apiRequest("/reliability/compliance", { cacheTtlMs: 15_000 });
`;
}

fs.writeFileSync(target, text.replace(/\s+$/, "") + "\n", "utf8");
console.log("Canonical Reliability service client completed.");
