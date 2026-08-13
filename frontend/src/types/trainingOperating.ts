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

export type TrainingPlanParticipant = { id: string; user_id: string; status: string; exclusion_reason?: string | null };
export type TrainingPlanItem = {
  id: string; course_id?: string | null; course_code_snapshot?: string | null; course_name_snapshot: string;
  training_kind: string; provider_mode: string; provider?: string | null; participant_count: number;
  planned_month?: number | null; quarter?: number | null; planned_start?: string | null; planned_end?: string | null;
  original_currency: string; estimated_unit_cost: string; estimated_total_cost: string; justification?: string | null;
  source_type: string; manual_reference?: string | null; authorization_impact?: string | null; participants: TrainingPlanParticipant[];
};
export type TrainingPlan = {
  id: string; plan_year: number; revision_no: number; title: string; status: string; form_reference?: string | null;
  notes?: string | null; prepared_by_user_id?: string | null; submitted_by_user_id?: string | null;
  reviewed_by_user_id?: string | null; approved_by_user_id?: string | null; items: TrainingPlanItem[];
};

export type TrainingBudgetLine = { id: string; course_code_snapshot?: string | null; course_name_snapshot: string; quarter: number; trainee_count: number; original_currency: string; reporting_currency: string; planned_amount: string; exchange_rate: string; rate_date: string; rate_source: string; converted_planned_amount: string; converted_approved_amount: string; converted_committed_amount: string; converted_actual_amount: string };
export type TrainingBudget = { id: string; plan_id: string; revision_no: number; status: string; reporting_currency: string; form_reference?: string | null; lines: TrainingBudgetLine[]; quarter_totals: Record<string, string>; annual_totals: Record<string, string> };
export type AuditorQualification = { user_id: string; completed_observer_audits: number; required_observer_audits: number; remaining_observer_audits: number; status: "QUALIFIED" | "IN_PROGRESS"; source: string; audit_ids: string[] };

export type AttendanceWindow = { id: string; event_id: string; status: string; attendance_code?: string | null; expires_at: string; opened_at: string; certified_at?: string | null; register_revision: number };
export type AttendanceEntry = { id: string; event_id: string; participant_id: string; user_id: string; status: string; method: string; signed_at: string; attestation?: string | null };

export type AssessmentTemplate = { id: string; code: string; name: string; assessment_type: string; outcome_scheme: string; revision_no: number; pass_threshold?: string | null; approval_required: boolean; active: boolean; manual_reference?: string | null };
export type Assessment = { id: string; template_id: string; candidate_user_id: string; course_id?: string | null; event_id?: string | null; authorization_case_id?: string | null; assessor_user_id?: string | null; status: string; score?: string | null; outcome?: string | null; comments?: string | null; created_at: string };

export type ReadinessItem = { key: string; label: string; status: string; blocking: boolean; reason: string; source: string };
export type AuthorizationReadiness = { case_id: string; overall_status: string; items: ReadinessItem[]; next_required_action: string; action_owner?: string | null; computed_at: string };
export type AuthorizationCase = { id: string; candidate_user_id: string; authorisation_type_id: string; requested_scope?: string | null; application_date: string; status: string; required_assessment_types: string[]; required_committee_positions: string[]; readiness_snapshot: Record<string, unknown>; recommendation?: string | null; decision?: string | null; issued_user_authorisation_id?: string | null; updated_at: string };

export type TrainingOperatingSettings = {
  default_planning_lead_days: number; default_recurrent_window_days: number; attendance_window_minutes: number;
  attendance_qr_lifetime_minutes: number; competence_review_frequency_months: number; experience_review_frequency_months: number;
  auditor_observer_count: number; reporting_currency: string; budget_rounding_places: number; plan_form_reference?: string | null;
  budget_form_reference?: string | null; attendance_form_reference?: string | null; assessment_form_mappings: Record<string, string>;
  authorization_form_mappings: Record<string, string>; approval_roles: Record<string, string[]>;
};
