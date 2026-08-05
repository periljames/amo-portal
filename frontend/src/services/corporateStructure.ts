import { apiGet, apiPatch, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";

export interface OrganizationOverview {
  units: number;
  active_units: number;
  positions: number;
  approved_headcount: number;
  active_assignments: number;
  vacant_positions: number;
  workforce_engagements: number;
  contingent_workers: number;
  missing_primary_assignment: number;
  missing_engagement: number;
  compliance_profiles_due: number;
  expiring_credentials_90_days: number;
}

export interface OrganizationUnit {
  id: string;
  amo_id: string;
  parent_id: string | null;
  parent_name: string | null;
  department_id: string | null;
  base_station_id: string | null;
  code: string;
  name: string;
  unit_type: string;
  purpose: string | null;
  cost_center: string | null;
  accountable_manager_user_id: string | null;
  accountable_manager_name: string | null;
  manager_user_id: string | null;
  manager_name: string | null;
  deputy_manager_user_id: string | null;
  deputy_manager_name: string | null;
  quality_owner_user_id: string | null;
  headcount_limit: number | null;
  sort_order: number;
  effective_from: string | null;
  effective_to: string | null;
  is_active: boolean;
  position_count: number;
  assignment_count: number;
  created_at: string;
  updated_at: string;
}

export interface OrganizationPosition {
  id: string;
  amo_id: string;
  unit_id: string;
  unit_name: string;
  reports_to_position_id: string | null;
  reports_to_position_title: string | null;
  code: string;
  title: string;
  job_family: string | null;
  grade: string | null;
  employment_category: string;
  headcount_limit: number;
  is_supervisory: boolean;
  is_regulatory_post: boolean;
  regulatory_post_type: string | null;
  authority_acceptance_required: boolean;
  minimum_competence_summary: string | null;
  responsibilities: string | null;
  approval_scope: string | null;
  default_account_role: string | null;
  succession_criticality: string;
  effective_from: string | null;
  effective_to: string | null;
  is_active: boolean;
  occupied_count: number;
  vacancy_count: number;
  created_at: string;
  updated_at: string;
}

export interface PositionAssignment {
  id: string;
  amo_id: string;
  user_id: string;
  user_name: string;
  staff_code: string;
  position_id: string;
  position_title: string;
  unit_name: string;
  reporting_manager_user_id: string | null;
  reporting_manager_name: string | null;
  assignment_type: string;
  status: string;
  is_primary: boolean;
  matrix_reporting: boolean;
  matrix_reason: string | null;
  fte_percent: number | string;
  effective_from: string;
  effective_to: string | null;
  appointment_reference: string | null;
  authority_acceptance_reference: string | null;
  authority_accepted_on: string | null;
  delegation_limitations: string | null;
  notes: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkforceEngagement {
  id: string;
  amo_id: string;
  user_id: string;
  user_name: string;
  staff_code: string;
  engagement_type: string;
  status: string;
  contract_reference: string | null;
  start_date: string;
  end_date: string | null;
  probation_months: number | null;
  sponsor_user_id: string | null;
  sponsor_name: string | null;
  external_organisation: string | null;
  institution_or_vendor: string | null;
  programme_name: string | null;
  learning_objectives: string | null;
  work_permit_status: string | null;
  work_permit_reference: string | null;
  work_permit_expires_on: string | null;
  background_check_status: string | null;
  access_expiry_on: string | null;
  offboarding_required: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface GroupPolicy {
  id: string;
  amo_id: string;
  group_id: string;
  group_name: string;
  unit_id: string | null;
  unit_name: string | null;
  code: string;
  name: string;
  description: string | null;
  inheritance_mode: string;
  membership_mode: string;
  default_account_role: string | null;
  permission_template: Record<string, unknown>;
  segregation_tags: string[];
  requires_manager_approval: boolean;
  requires_quality_approval: boolean;
  maximum_assignment_days: number | null;
  effective_from: string | null;
  effective_to: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ComplianceProfile {
  id: string;
  amo_id: string;
  user_id: string;
  legal_name: string | null;
  preferred_name: string | null;
  nationality: string | null;
  residence_country: string | null;
  identity_verified: boolean;
  identity_reference: string | null;
  identity_verified_at: string | null;
  identity_verified_by_user_id: string | null;
  emergency_contact_name: string | null;
  emergency_contact_relationship: string | null;
  emergency_contact_phone: string | null;
  data_classification: string;
  retention_class: string;
  confidentiality_ack_at: string | null;
  code_of_conduct_ack_at: string | null;
  conflict_declaration_at: string | null;
  competence_status: string;
  training_status: string;
  authorisation_status: string;
  medical_fitness_status: string;
  last_competence_assessment_on: string | null;
  next_review_on: string | null;
  compliance_owner_user_id: string | null;
  restrictions: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PersonnelCredential {
  id: string;
  amo_id: string;
  user_id: string;
  credential_type: string;
  authority: string | null;
  reference: string;
  title: string | null;
  scope: Record<string, unknown>;
  issued_on: string | null;
  expires_on: string | null;
  status: string;
  evidence_document_id: string | null;
  restrictions: string | null;
  verified_by_user_id: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserGovernance {
  user: {
    id: string;
    full_name: string;
    staff_code: string;
    email: string;
    position_title: string | null;
    is_active: boolean;
    role: string;
  };
  primary_assignment: PositionAssignment | null;
  assignments: PositionAssignment[];
  active_engagement: WorkforceEngagement | null;
  engagements: WorkforceEngagement[];
  compliance_profile: ComplianceProfile | null;
  credentials: PersonnelCredential[];
  readiness_score: number;
  readiness_gaps: string[];
}

export interface OrganizationReferenceData {
  users: Array<{
    id: string;
    full_name: string;
    staff_code: string;
    email: string;
    position_title: string | null;
    is_active: boolean;
  }>;
  groups: Array<{ id: string; code: string; name: string; group_type: string }>;
  departments: Array<{ id: string; code: string; name: string }>;
}

export interface ManagerTeamMember {
  user_id: string;
  full_name: string;
  staff_code: string;
  email: string;
  position_title: string;
  unit_name: string;
  engagement_type: string | null;
  engagement_end_date: string | null;
  competence_status: string;
  training_status: string;
  expiring_credentials: number;
  readiness_score: number;
  readiness_gaps: string[];
}

function query(amoId?: string | null): string {
  const params = new URLSearchParams();
  if (amoId?.trim()) params.set("amo_id", amoId.trim());
  return params.toString() ? `?${params.toString()}` : "";
}

const options = () => ({ headers: authHeaders() });

export const getOrganizationOverview = (amoId?: string | null) =>
  apiGet<OrganizationOverview>(`/accounts/admin/organization/overview${query(amoId)}`, options());
export const listOrganizationUnits = (amoId?: string | null, includeInactive = false) =>
  apiGet<OrganizationUnit[]>(`/accounts/admin/organization/units${query(amoId)}${query(amoId) ? "&" : "?"}include_inactive=${String(includeInactive)}`, options());
export const listOrganizationPositions = (amoId?: string | null) =>
  apiGet<OrganizationPosition[]>(`/accounts/admin/organization/positions${query(amoId)}`, options());
export const listPositionAssignments = (amoId?: string | null, activeOnly = true) =>
  apiGet<PositionAssignment[]>(`/accounts/admin/organization/assignments${query(amoId)}${query(amoId) ? "&" : "?"}active_only=${String(activeOnly)}`, options());
export const listWorkforceEngagements = (amoId?: string | null, activeOnly = true) =>
  apiGet<WorkforceEngagement[]>(`/accounts/admin/organization/engagements${query(amoId)}${query(amoId) ? "&" : "?"}active_only=${String(activeOnly)}`, options());
export const listGroupPolicies = (amoId?: string | null) =>
  apiGet<GroupPolicy[]>(`/accounts/admin/organization/group-policies${query(amoId)}`, options());
export const getOrganizationReferenceData = (amoId?: string | null) =>
  apiGet<OrganizationReferenceData>(`/accounts/admin/organization/reference-data${query(amoId)}`, options());

export const createOrganizationUnit = (payload: Record<string, unknown>) =>
  apiPost<OrganizationUnit>("/accounts/admin/organization/units", payload, options());
export const updateOrganizationUnit = (unitId: string, payload: Record<string, unknown>, amoId?: string | null) =>
  apiPatch<OrganizationUnit>(`/accounts/admin/organization/units/${encodeURIComponent(unitId)}${query(amoId)}`, payload, options());
export const createOrganizationPosition = (payload: Record<string, unknown>) =>
  apiPost<OrganizationPosition>("/accounts/admin/organization/positions", payload, options());
export const createPositionAssignment = (payload: Record<string, unknown>) =>
  apiPost<PositionAssignment>("/accounts/admin/organization/assignments", payload, options());
export const createWorkforceEngagement = (payload: Record<string, unknown>) =>
  apiPost<WorkforceEngagement>("/accounts/admin/organization/engagements", payload, options());
export const createGroupPolicy = (payload: Record<string, unknown>) =>
  apiPost<GroupPolicy>("/accounts/admin/organization/group-policies", payload, options());

export const getUserGovernance = (userId: string, amoId?: string | null) =>
  apiGet<UserGovernance>(`/accounts/admin/organization/users/${encodeURIComponent(userId)}/governance${query(amoId)}`, options());
export const saveComplianceProfile = (userId: string, payload: Record<string, unknown>, amoId?: string | null) =>
  apiPut<ComplianceProfile>(`/accounts/admin/organization/users/${encodeURIComponent(userId)}/compliance-profile${query(amoId)}`, payload, options());
export const createPersonnelCredential = (payload: Record<string, unknown>) =>
  apiPost<PersonnelCredential>("/accounts/admin/organization/credentials", payload, options());

export const getMyOrganizationProfile = () =>
  apiGet<{ user: UserGovernance["user"]; assignment: PositionAssignment | null; engagement: WorkforceEngagement | null; compliance_profile: ComplianceProfile | null; credentials: PersonnelCredential[] }>("/auth/organization/my-profile", options());
export const getMyTeam = () => apiGet<ManagerTeamMember[]>("/auth/organization/my-team", options());
