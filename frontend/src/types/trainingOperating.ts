export type TrainingCapability =
  | "training.view" | "training.self.view" | "training.people.view" | "training.people.manage"
  | "training.course.view" | "training.course.manage" | "training.requirement.view" | "training.requirement.manage"
  | "training.plan.view" | "training.plan.manage" | "training.plan.review" | "training.plan.approve"
  | "training.budget.view" | "training.budget.manage" | "training.budget.review" | "training.budget.approve"
  | "training.session.view" | "training.session.manage" | "training.session.close"
  | "training.attendance.view" | "training.attendance.sign_self" | "training.attendance.manage" | "training.attendance.correct"
  | "training.assessment.view" | "training.assessment.create" | "training.assessment.perform" | "training.assessment.review" | "training.assessment.approve"
  | "training.authorization.view" | "training.authorization.prepare" | "training.authorization.recommend"
  | "training.authorization.committee_decide" | "training.authorization.issue" | "training.authorization.renew"
  | "training.authorization.restrict" | "training.authorization.withdraw"
  | "training.certificate.view" | "training.certificate.issue" | "training.certificate.revoke" | "training.certificate.reissue"
  | "training.report.view" | "training.report.export" | "training.settings.manage";

export type TrainingAccess = { capabilities: TrainingCapability[]; can_open_operating_system: boolean; self_service_only: boolean; tenant_id: string };
export type ActionQueueItem = { key: string; label: string; count: number | null; severity: "INFO" | "WARNING" | "CRITICAL"; reason: string; action_label: string; path: string; available: boolean };
export type TrainingControlRoom = { generated_at: string; queues: ActionQueueItem[]; source_errors: string[] };
export type SourceHealth = { generated_at: string; overall_status: "HEALTHY" | "DEGRADED" | "UNAVAILABLE"; sources: Array<{ source: string; status: "HEALTHY" | "DEGRADED" | "UNAVAILABLE" | "NOT_CONFIGURED"; checked_at: string; freshness_at?: string | null; detail: string; retryable: boolean; action_path?: string | null }> };
export type PersonComplianceRow = { id: string; full_name: string; staff_code?: string | null; email?: string | null; position_title?: string | null; department?: string | null; active: boolean; outstanding: number; overdue: number; due_soon: number; never_completed: number; next_due?: string | null; next_action: string; status: "CURRENT" | "DUE_SOON" | "OVERDUE" | "INCOMPLETE" | "UNKNOWN"; provenance: { calculated_at?: string; obligations?: Array<Record<string, unknown>> } };
export type PersonCompliancePage = { items: PersonComplianceRow[]; total: number; limit: number; offset: number; has_more: boolean; filtered_totals: Record<string, number | string | null> };
export type CanonicalReference = { id: string; code?: string | null; label: string; description?: string | null; source: string };

export type SetupVersion = { id: string; amo_id: string; version_no: number; source_mode: "BLANK" | "TEMPLATE_PACK" | "WORKBOOK"; status: string; title: string; change_summary?: string | null; snapshot: Record<string, unknown>; validation_result: { status?: string; blockers?: string[]; checks?: Record<string, boolean> }; effective_from?: string | null; created_by_user_id?: string | null; reviewed_by_user_id?: string | null; activated_by_user_id?: string | null; supersedes_version_id?: string | null; created_at: string; updated_at: string };
export type ControlledChange = { id: string; amo_id: string; object_type: string; object_id?: string | null; operation: string; status: string; requested_payload: Record<string, unknown>; impact_summary: Record<string, unknown>; validation_result: Record<string, unknown>; source_cutoff_at: string; requested_by_user_id?: string | null; decided_by_user_id?: string | null; decision_reason?: string | null; applied_at?: string | null; created_at: string; updated_at: string };
export type WorkflowStep = { id: string; step_key: string; label: string; sequence_no: number; assigned_user_id?: string | null; status: string; response_json: Record<string, unknown>; signature_json: Record<string, unknown>; completed_by_user_id?: string | null; completed_at?: string | null };
export type TrainingWorkflow = { id: string; amo_id: string; workflow_type: string; form_template_id?: string | null; form_revision_no?: number | null; subject_user_id?: string | null; owner_user_id?: string | null; reviewer_user_id?: string | null; event_id?: string | null; course_id?: string | null; authorization_case_id?: string | null; status: string; title: string; due_at?: string | null; data_json: Record<string, unknown>; validation_result: Record<string, unknown>; provenance: Record<string, unknown>; revision_no: number; submitted_at?: string | null; completed_at?: string | null; created_by_user_id?: string | null; created_at: string; updated_at: string; steps: WorkflowStep[] };
export type WorkflowPage = { items: TrainingWorkflow[]; total: number; limit: number; offset: number; has_more: boolean; filtered_totals: Record<string, number | string | null> };
export type SessionInvitation = { id: string; event_id: string; user_id: string; channel: string; delivery_status: string; attempt_count: number; last_error?: string | null; rsvp_status: string; responded_at?: string | null; sent_at?: string | null; delivered_at?: string | null; read_at?: string | null; created_at: string; updated_at: string };
export type InvitationPage = { items: SessionInvitation[]; total: number; limit: number; offset: number; has_more: boolean; filtered_totals: Record<string, number | string | null> };
export type ReportDefinition = { id: string; code: string; name: string; description?: string | null; dataset: string; allowed_formats: Array<"PDF" | "XLSX" | "CSV">; default_filters: Record<string, unknown>; schedule_json: Record<string, unknown>; retention_days: number; active: boolean; created_at: string; updated_at: string };
export type ReportJob = { id: string; report_code: string; output_format: "PDF" | "XLSX" | "CSV"; status: string; filters_json: Record<string, unknown>; scope_manifest: Record<string, unknown>; artifact_checksum?: string | null; error_text?: string | null; requested_by_user_id?: string | null; started_at?: string | null; completed_at?: string | null; expires_at?: string | null; created_at: string };
export type ReportJobPage = { items: ReportJob[]; total: number; limit: number; offset: number; has_more: boolean; filtered_totals: Record<string, number | string | null> };
export type CertificateEligibilityItem = { record_id: string; user_id: string; person_name: string; staff_code?: string | null; course_id: string; course_code: string; course_name: string; completion_date: string; valid_until?: string | null; eligible: boolean; blockers: Array<{ code: string; message: string }> };
export type CertificateEligibilityPage = { items: CertificateEligibilityItem[]; total: number; limit: number; offset: number; has_more: boolean; filtered_totals: Record<string, number | string | null> };
export type CertificateBatchIssueResult = { requested: number; issued: number; blocked: number; items: Array<{ record_id: string; status: "ISSUED" | "BLOCKED" | "NOT_FOUND" | "ALREADY_ISSUED"; certificate_id?: string | null; certificate_number?: string | null; blockers: Array<{ code: string; message: string }> }> };

export type TrainingPlanParticipant = {
  id: string; user_id: string; person_name_snapshot: string; staff_code_snapshot?: string | null;
  last_completion_date?: string | null; expiry_date?: string | null; planned_due_date?: string | null;
  obligation_status: string; source_type: string; source_record_id?: string | null; source_reference?: string | null;
  status: string; exclusion_reason?: string | null;
};
export type TrainingPlanItem = {
  id: string; course_id?: string | null; course_code_snapshot?: string | null; course_name_snapshot: string;
  training_kind: string; provider_mode: string; provider?: string | null; participant_count: number;
  planned_month?: number | null; quarter?: number | null; planned_start?: string | null; planned_end?: string | null;
  instructor_ids?: string[];
  original_currency: string; estimated_unit_cost: string; estimated_total_cost: string; justification?: string | null;
  source_type: string; manual_reference?: string | null; authorization_impact?: string | null; participants: TrainingPlanParticipant[];
};
export type TrainingPlan = {
  id: string; plan_year: number; revision_no: number; title: string; status: string; form_reference?: string | null;
  notes?: string | null; prepared_by_user_id?: string | null; submitted_by_user_id?: string | null;
  reviewed_by_user_id?: string | null; approved_by_user_id?: string | null; items: TrainingPlanItem[];
};
export type TrainingPlanSummary = {
  id: string; plan_year: number; revision_no: number; title: string; status: string; form_reference?: string | null;
  notes?: string | null; item_count: number; participant_count: number; estimated_total_cost: string;
  original_currency: string; created_at: string; updated_at: string;
};
export type TrainingPlanObligation = {
  key: string; plan_item_id: string; participant_id: string; month: number; course_code?: string | null;
  course_name: string; manual_reference?: string | null; user_id: string; person_name: string; staff_code?: string | null;
  last_completion_date?: string | null; expiry_date?: string | null; planned_due_date?: string | null;
  obligation_status: string; source_type: string; source_record_id?: string | null; source_reference?: string | null; status: string;
};
export type TrainingPlanObligationPage = { items: TrainingPlanObligation[]; total: number; limit: number; offset: number; month_counts: number[] };
export type TrainingPlanMatrixPerson = {
  user_id: string; person_name: string; staff_code?: string | null; planned_due_date?: string | null;
  expiry_date?: string | null; obligation_status: string;
};
export type TrainingPlanMatrixCell = { month: number; personnel_count: number; preview: TrainingPlanMatrixPerson[] };
export type TrainingPlanMatrixCourse = {
  course_key: string; course_id?: string | null; course_code?: string | null; course_name: string;
  training_kind: string; provider_mode: string; personnel_count: number; cells: TrainingPlanMatrixCell[];
};
export type TrainingPlanMatrixPage = {
  plan_id: string; plan_year: number; months: number[]; items: TrainingPlanMatrixCourse[]; total: number;
  limit: number; offset: number; has_more: boolean; kind_counts: Record<string, number>;
};
export type TrainingPlanMatrixPersonPage = {
  course_key: string; month: number; items: TrainingPlanMatrixPerson[]; total: number;
  limit: number; offset: number; has_more: boolean;
};
export type ExchangeRateQuote = {
  base_currency: string; quote_currency: string; rate: string; rate_date: string; quoted_at: string;
  next_update_at?: string | null; provider: string; source_url?: string | null; attribution_url?: string | null; cached: boolean;
};

export type TrainingBudgetLine = { id: string; course_code_snapshot?: string | null; course_name_snapshot: string; quarter: number; trainee_count: number; original_currency: string; reporting_currency: string; unit_cost: string; planned_amount: string; approved_amount: string; committed_amount: string; actual_amount: string; exchange_rate: string; rate_date: string; rate_source: string; converted_planned_amount: string; converted_approved_amount: string; converted_committed_amount: string; converted_actual_amount: string; notes?: string | null };
export type TrainingBudget = { id: string; plan_id: string; revision_no: number; status: string; reporting_currency: string; form_reference?: string | null; lines: TrainingBudgetLine[]; quarter_totals: Record<string, string>; annual_totals: Record<string, string> };
export type AuditorQualification = { user_id: string; completed_observer_audits: number; required_observer_audits: number; remaining_observer_audits: number; status: "QUALIFIED" | "IN_PROGRESS"; source: string; audit_ids: string[] };

export type AttendanceWindow = { id: string; event_id: string; status: string; attendance_code?: string | null; sign_in_path?: string | null; notifications_sent: number; notifications_queued: number; notification_delivery_status: "QUEUED" | "NONE" | "UNKNOWN"; expires_at: string; opened_at: string; closed_at?: string | null; certified_at?: string | null; register_revision: number };
export type AttendanceEntry = { id: string; event_id: string; participant_id: string; user_id: string; status: string; method: string; signed_at: string; attestation?: string | null };
export type AttendanceRosterItem = { participant_id: string; user_id: string; full_name: string; staff_code?: string | null; participant_status: string; attendance_entry_id?: string | null; attendance_status?: string | null; method?: string | null; signed_at?: string | null };
export type AttendanceRosterPage = { items: AttendanceRosterItem[]; total: number; signed_count: number; limit: number; offset: number };

export type AssessmentQuestion = { id: string; sequence_no: number; question_text: string; response_type: string; answer_options: string[]; marks: string; mandatory: boolean; manual_reference?: string | null; active: boolean };
export type AssessmentTemplate = { id: string; code: string; name: string; assessment_type: string; outcome_scheme: string; revision_no: number; pass_threshold?: string | null; approval_required: boolean; active: boolean; manual_reference?: string | null; questions: AssessmentQuestion[] };
export type Assessment = { id: string; template_id: string; candidate_user_id: string; course_id?: string | null; event_id?: string | null; authorization_case_id?: string | null; assessor_user_id?: string | null; status: string; score?: string | null; outcome?: string | null; comments?: string | null; created_at: string };

export type ReadinessItem = { key: string; label: string; status: string; blocking: boolean; reason: string; source: string };
export type AuthorizationReadiness = { case_id: string; overall_status: string; items: ReadinessItem[]; next_required_action: string; action_owner?: string | null; computed_at: string };
export type AuthorizationCase = { id: string; candidate_user_id: string; authorisation_type_id: string; requested_scope?: string | null; application_date: string; status: string; required_assessment_types: string[]; required_committee_positions: string[]; readiness_snapshot: Record<string, unknown>; recommendation?: string | null; decision?: string | null; issued_user_authorisation_id?: string | null; updated_at: string };

export type NextBatchCandidate = {
  user_id: string; full_name: string; staff_code?: string | null; department?: string | null; status: string;
  due_date?: string | null; days_remaining?: number | null; existing_booking?: string | null;
  availability_conflict?: string | null; authorization_impact?: string | null; eligible: boolean; rank_reason: string;
};
export type NextBatch = { course_id: string; course_code: string; course_name: string; candidates: NextBatchCandidate[] };
export type CourseAuditException = { user_id: string; full_name: string; staff_code?: string | null; exception_code: string; severity: "INFO" | "WARNING" | "CRITICAL"; detail: string; correction_path: string };
export type CourseAudit = { course_id: string; course_code: string; course_name: string; required_people: number; current_people: number; overdue_people: number; never_completed_people: number; exceptions: CourseAuditException[] };
export type EffectivenessEvaluation = { id: string; course_id: string; event_id?: string | null; user_id?: string | null; level: number; evaluation_period_start?: string | null; evaluation_period_end?: string | null; evidence: Record<string, unknown>; rating?: string | null; conclusion?: string | null; causation_claimed: boolean; status: string; created_at: string };
export type RemedialAction = { id: string; candidate_user_id: string; course_id?: string | null; gap: string; required_activity: string; owner_user_id?: string | null; due_date: string; supervised_experience_required: boolean; reassessment_required: boolean; status: string };

export type TrainingOperatingSettings = {
  default_planning_lead_days: number; default_recurrent_window_days: number; attendance_window_minutes: number;
  attendance_qr_lifetime_minutes: number; competence_review_frequency_months: number; experience_review_frequency_months: number;
  auditor_observer_count: number; reporting_currency: string; budget_rounding_places: number; plan_form_reference?: string | null;
  budget_form_reference?: string | null; attendance_form_reference?: string | null; assessment_form_mappings: Record<string, string>;
  authorization_form_mappings: Record<string, string>; approval_roles: Record<string, string[]>;
  timezone: string; plan_automation_enabled: boolean; plan_run_day: number; plan_run_hour: number;
  notification_policy: Record<string, unknown>; certificate_number_prefix: string; certificate_template_reference?: string | null;
  certificate_signatories: Array<{ name: string; title: string }>; certificate_public_privacy_text?: string | null;
  default_committee_positions: string[]; setup_status: "DRAFT" | "ACTIVE"; configuration_revision_no: number;
  configured?: boolean;
};

export type SetupReadinessItem = { key: string; label: string; status: "READY" | "WARNING" | "BLOCKED"; blocking: boolean; reason: string; action_path: string };
export type SetupReadiness = { generated_at: string; go_live_ready: boolean; completion_percent: number; items: SetupReadinessItem[] };
export type TrainingReferenceResource = {
  id: string; resource_type: "PROVIDER" | "LOCATION" | "INSTRUCTOR"; code: string; name: string;
  contact_name?: string | null; email?: string | null; phone?: string | null; address?: string | null;
  metadata_json: Record<string, unknown>; active: boolean; created_at: string; updated_at: string;
};
export type ControlledFormTemplate = {
  id: string; code: string; title: string; workflow: string; revision_no: number; status: string;
  dms_document_id?: string | null; dms_revision_id?: string | null; schema_json: Record<string, unknown>;
  retention_rule?: string | null; effective_from?: string | null; effective_to?: string | null; updated_at: string;
};
export type ConfigurationRevision = { id: string; revision_no: number; snapshot: Record<string, unknown>; change_summary?: string | null; created_by_user_id?: string | null; created_at: string };
export type AutomationRun = { id: string; period_year: number; period_month: number; trigger: string; status: string; plan_id?: string | null; summary: Record<string, unknown>; error_text?: string | null; started_at: string; completed_at?: string | null };
export type AutomationStatus = { enabled: boolean; timezone: string; run_day: number; run_hour: number; next_run_at?: string | null; last_run?: AutomationRun | null };
