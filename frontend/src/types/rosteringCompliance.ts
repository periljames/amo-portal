export type RosterConsentStatus = "PENDING" | "ACCEPTED" | "DECLINED" | "INVALIDATED";
export type RosterSupervisorDecision = "NOT_REQUIRED" | "PENDING" | "APPROVED" | "REJECTED";
export type RosterWorkflowGateSeverity = "HARD_BLOCK" | "CONDITIONAL_BLOCK" | "WARNING";
export type RosterDutyExtensionStatus =
  | "AWAITING_PERSONNEL_ACKNOWLEDGEMENT"
  | "AWAITING_SUPERVISOR_APPROVAL"
  | "COMPLIANCE_BLOCKED"
  | "READY"
  | "CANCELLED";

export type RosterAssignmentConsentRead = {
  id: string; version_id: string; assignment_id: string; assignment_revision: number;
  assignment_fingerprint: string; personnel_id: string; proposed_by_user_id?: string | null;
  reason: string; duty_type: string; planned_start: string; planned_end: string;
  original_schedule_json?: Record<string, unknown> | null; personnel_response: RosterConsentStatus;
  personnel_response_at?: string | null; personnel_comment?: string | null; supervisor_required: boolean;
  supervisor_user_id?: string | null; supervisor_decision: RosterSupervisorDecision;
  supervisor_decision_at?: string | null; supervisor_decided_by_user_id?: string | null;
  supervisor_comment?: string | null; overtime_rest_day_classification?: string | null;
  replacement_rest_json?: Record<string, unknown> | null; statutory_compliance_json?: Record<string, unknown> | null;
  fatigue_risk_json?: Record<string, unknown> | null; invalidated_at?: string | null;
  invalidation_reason?: string | null; created_at: string; updated_at: string;
};

export type RosterConsentPersonnelDecision = { decision: "ACCEPT" | "DECLINE"; assignment_fingerprint: string; comment?: string | null };
export type RosterConsentSupervisorDecision = { decision: "APPROVE" | "REJECT"; assignment_fingerprint: string; comment?: string | null };

export type RosterWorkflowGateRead = {
  severity: RosterWorkflowGateSeverity; code: string; message: string;
  assignment_id?: string | null; personnel_id?: string | null; rule_id?: string | null;
  consent_id?: string | null; extension_id?: string | null; details: Record<string, unknown>;
  remediation_actions: string[];
};

export type RosterWorkflowGateResponse = {
  version_id: string; workflow_state: "STATUTORY_BLOCKED" | "AWAITING_WORKFLOW_ACTION" | "READY_WITH_WARNINGS" | "READY" | string;
  hard_block_count: number; conditional_block_count: number; warning_count: number;
  can_submit: boolean; can_approve: boolean; can_publish: boolean; gates: RosterWorkflowGateRead[];
};

export type RosterExemptionEvidenceRead = {
  id: string; document_number: string; title: string; document_type: string; status: string;
  version: string; revision_no: number; effective_date?: string | null; restricted: boolean;
};

export type RosterRegulatoryExemptionRead = {
  id: string; authority: string; exemption_reference: string; regulation_provision: string; scope: string;
  personnel_id?: string | null; role_applicability?: string | null; conditions_json: Record<string, unknown>;
  effective_date: string; expiry_date: string; supporting_document_id: string; verified_by_user_id?: string | null;
  verified_at?: string | null; is_revoked: boolean; revoked_at?: string | null; revocation_reason?: string | null;
  created_by_user_id?: string | null; created_at: string; updated_at: string;
};

export type RosterRegulatoryExemptionCreate = {
  authority: string; exemption_reference: string; regulation_provision: string; scope: string;
  personnel_id?: string | null; role_applicability?: string | null; conditions?: Record<string, unknown>;
  effective_date: string; expiry_date: string; supporting_document_id: string;
};

export type RosterDutyExtensionRead = {
  id: string; version_id: string; assignment_id: string; consent_id?: string | null;
  extension_type: "UNSCHEDULED_AIRCRAFT_UNSERVICEABILITY"; aircraft_registration: string;
  operational_reference: string; work_order_reference?: string | null; reason: string; normal_duty_start: string;
  original_planned_end: string; proposed_extended_end: string; continuous_duty_minutes: number;
  required_recovery_rest_minutes: number; recovery_rest_basis?: string | null;
  compliance_snapshot_json: Record<string, unknown>; fatigue_risk_json: Record<string, unknown>;
  status: RosterDutyExtensionStatus; proposed_by_user_id?: string | null; created_at: string; updated_at: string;
};

export type RosterDutyExtensionCreate = {
  assignment_id: string; proposed_extended_end: string; aircraft_registration: string;
  operational_reference: string; work_order_reference?: string | null; reason: string;
};
