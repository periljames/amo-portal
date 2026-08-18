import { apiJson, jsonBody } from "./typedApi";

export type RosterShiftDutySemantic = "DUTY" | "STANDBY" | "TRAINING" | "REST" | "OFF" | "LEAVE" | "SICK" | "OTHER";
export type RosterShiftCalendarMode = "TIMED" | "ALL_DAY" | "HIDDEN";
export type RosterShiftVerification = "CONFIRMED" | "REVIEW_REQUIRED" | "UNRESOLVED";

export type RosterShiftOperationalPolicy = {
  shift_template_id: string;
  code: string;
  label: string;
  kind: string;
  default_start_time?: string | null;
  default_end_time?: string | null;
  spans_midnight: boolean;
  counts_as_duty: boolean;
  counts_as_rest: boolean;
  on_site_availability: boolean;
  scheduling_eligible: boolean;
  effective_scheduling_eligible: boolean;
  calendar_mode: RosterShiftCalendarMode;
  duty_semantic: RosterShiftDutySemantic;
  verification_status: RosterShiftVerification;
  unpaid_break_minutes: number;
  requires_personnel_acknowledgement: boolean;
  requires_supervisor_approval: boolean;
  fatigue_weight: number;
  pay_classification?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  source_reference?: string | null;
};

export type RosterShiftOperationalPolicyUpdate = Partial<Pick<
  RosterShiftOperationalPolicy,
  | "counts_as_duty"
  | "counts_as_rest"
  | "on_site_availability"
  | "scheduling_eligible"
  | "calendar_mode"
  | "duty_semantic"
  | "verification_status"
  | "unpaid_break_minutes"
  | "requires_personnel_acknowledgement"
  | "requires_supervisor_approval"
  | "fatigue_weight"
  | "pay_classification"
  | "effective_from"
  | "effective_to"
  | "source_reference"
>>;

export function listRosterShiftOperationalPolicies(): Promise<RosterShiftOperationalPolicy[]> {
  return apiJson("/rostering/shift-operational-policies", {
    offline: { cacheTtlMs: 5 * 60_000 },
  });
}

export function updateRosterShiftOperationalPolicy(
  templateId: string,
  payload: RosterShiftOperationalPolicyUpdate,
): Promise<RosterShiftOperationalPolicy> {
  return apiJson(`/rostering/shift-templates/${encodeURIComponent(templateId)}/operational-policy`, {
    method: "PATCH",
    body: jsonBody(payload),
  });
}
