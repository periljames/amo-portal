import { apiGet, apiPatch, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";

export interface ReportingReferenceUser {
  id: string;
  full_name: string;
  staff_code: string;
  email: string;
  department_id: string | null;
  current_title: string | null;
}

export interface ReportingUnit {
  id: string;
  code: string;
  name: string;
  unit_type: string;
  parent_id: string | null;
  department_id: string | null;
  editable: boolean;
}

export interface ReportingOccupant {
  assignment_id: string;
  user_id: string;
  user_name: string;
  staff_code: string;
  canonical_title: string;
  display_title: string;
  title_preference_status: string | null;
  reporting_manager_user_id: string | null;
  reporting_manager_name: string | null;
  assignment_type: string;
  is_primary: boolean;
  fte_percent: string;
  matrix_reporting: boolean;
  matrix_reason: string | null;
  effective_from: string;
  effective_to: string | null;
}

export interface ReportingManagerCandidate {
  user_id: string;
  user_name: string;
  position_id: string;
  position_title: string;
  relationship: string;
}

export interface ReportingPosition {
  id: string;
  unit_id: string;
  unit_name: string;
  code: string;
  canonical_title: string;
  reports_to_position_id: string | null;
  reports_to_title: string | null;
  depth: number;
  path_titles: string[];
  is_supervisory: boolean;
  is_regulatory_post: boolean;
  authority_acceptance_required: boolean;
  headcount_limit: number;
  occupied_count: number;
  vacancy_count: number;
  editable: boolean;
  manager_candidates: ReportingManagerCandidate[];
  occupants: ReportingOccupant[];
}

export interface TitlePreference {
  id: string;
  user_id: string;
  user_name: string;
  assignment_id: string;
  canonical_title: string;
  requested_title: string;
  reason: string | null;
  source: string;
  status: string;
  requested_by_user_id: string | null;
  decided_by_user_id: string | null;
  requested_at: string;
  decided_at: string | null;
}

export interface ReportingWorkspace {
  actor_mode: "ADMIN" | "MANAGER";
  can_manage_all: boolean;
  manageable_unit_ids: string[];
  units: ReportingUnit[];
  positions: ReportingPosition[];
  users: ReportingReferenceUser[];
  pending_title_preferences: TitlePreference[];
  authorization_boundary: string;
}

export interface ChainRoleInput {
  title: string;
  code?: string | null;
  headcount_limit: number;
  is_supervisory: boolean;
}

export interface ReportingChainInput {
  unit_id: string;
  parent_position_id?: string | null;
  roles: ChainRoleInput[];
}

export interface GuidedAssignmentInput {
  user_id: string;
  position_id: string;
  reporting_manager_user_id?: string | null;
  assignment_type: string;
  is_primary: boolean;
  effective_from: string;
  effective_to?: string | null;
  fte_percent: string;
  matrix_reporting: boolean;
  matrix_reason?: string | null;
  display_title?: string | null;
  appointment_reference?: string | null;
  authority_acceptance_reference?: string | null;
  authority_accepted_on?: string | null;
  delegation_limitations?: string | null;
}

export interface ReportingAssignmentUpdateInput {
  reporting_manager_user_id?: string | null;
  assignment_type?: string;
  effective_to?: string | null;
  fte_percent?: string;
  matrix_reporting?: boolean;
  matrix_reason?: string | null;
  display_title?: string;
  delegation_limitations?: string | null;
  notes?: string | null;
}

export interface ReportingAssignmentTransferInput {
  target_position_id: string;
  effective_from: string;
  reporting_manager_user_id?: string | null;
  assignment_type: string;
  fte_percent: string;
  matrix_reporting: boolean;
  matrix_reason?: string | null;
  display_title?: string | null;
  appointment_reference?: string | null;
  authority_acceptance_reference?: string | null;
  authority_accepted_on?: string | null;
  delegation_limitations?: string | null;
  reason: string;
}

export interface MyTitleProfile {
  assignment_id: string | null;
  position_id: string | null;
  canonical_title: string | null;
  display_title: string | null;
  unit_name: string | null;
  reporting_manager_name: string | null;
  reporting_chain: string[];
  current_preference: TitlePreference | null;
  authorization_boundary: string;
}

const options = () => ({ headers: authHeaders() });

export const getReportingWorkspace = () =>
  apiGet<ReportingWorkspace>("/auth/organization/reporting/workspace", options());

function mutationBase(actorMode: ReportingWorkspace["actor_mode"]): string {
  return actorMode === "ADMIN"
    ? "/accounts/admin/organization/reporting"
    : "/auth/organization/reporting/manager";
}

export const createReportingChain = (
  actorMode: ReportingWorkspace["actor_mode"],
  payload: ReportingChainInput,
) => apiPost<{ created_positions: ReportingPosition[] }>(
  `${mutationBase(actorMode)}/chains`,
  payload,
  options(),
);

export const updateReportingPosition = (
  actorMode: ReportingWorkspace["actor_mode"],
  positionId: string,
  payload: Record<string, unknown>,
) => apiPatch<ReportingWorkspace>(
  `${mutationBase(actorMode)}/positions/${encodeURIComponent(positionId)}`,
  payload,
  options(),
);

export const createGuidedAssignment = (
  actorMode: ReportingWorkspace["actor_mode"],
  payload: GuidedAssignmentInput,
) => apiPost<ReportingWorkspace>(
  `${mutationBase(actorMode)}/assignments`,
  payload,
  options(),
);

export const updateReportingAssignment = (
  actorMode: ReportingWorkspace["actor_mode"],
  assignmentId: string,
  payload: ReportingAssignmentUpdateInput,
) => apiPatch<ReportingWorkspace>(
  `${mutationBase(actorMode)}/assignments/${encodeURIComponent(assignmentId)}`,
  payload,
  options(),
);

export const endReportingAssignment = (
  actorMode: ReportingWorkspace["actor_mode"],
  assignmentId: string,
  endOn: string,
  reason: string,
) => apiPost<ReportingWorkspace>(
  `${mutationBase(actorMode)}/assignments/${encodeURIComponent(assignmentId)}/end`,
  { end_on: endOn, reason: reason.trim() },
  options(),
);

export const transferReportingAssignment = (
  actorMode: ReportingWorkspace["actor_mode"],
  assignmentId: string,
  payload: ReportingAssignmentTransferInput,
) => apiPost<ReportingWorkspace>(
  `${mutationBase(actorMode)}/assignments/${encodeURIComponent(assignmentId)}/transfer`,
  payload,
  options(),
);

export const decideTitlePreference = (
  actorMode: ReportingWorkspace["actor_mode"],
  preferenceId: string,
  decision: "APPROVE" | "REJECT",
  note?: string,
) => apiPost<ReportingWorkspace>(
  `${mutationBase(actorMode)}/title-preferences/${encodeURIComponent(preferenceId)}/decision`,
  { decision, note: note?.trim() || null },
  options(),
);

export const getMyTitleProfile = () =>
  apiGet<MyTitleProfile>("/auth/organization/reporting/my-title", options());

export const submitMyTitlePreference = (requestedTitle: string, reason?: string) =>
  apiPut<MyTitleProfile>(
    "/auth/organization/reporting/my-title",
    { requested_title: requestedTitle.trim(), reason: reason?.trim() || null },
    options(),
  );

export const clearMyTitlePreference = () =>
  apiPost<MyTitleProfile>("/auth/organization/reporting/my-title/clear", {}, options());
