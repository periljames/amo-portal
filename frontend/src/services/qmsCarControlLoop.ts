import { apiRequest, qmsPath } from "./apiClient";

export type CarControlMilestoneStatus =
  | "PLANNED"
  | "IN_PROGRESS"
  | "SUBMITTED"
  | "ACCEPTED"
  | "REJECTED"
  | "BLOCKED"
  | "COMPLETED"
  | "WAIVED";

export type CarDependencyStatus = "OPEN" | "MITIGATING" | "MITIGATED" | "RESOLVED" | "ACCEPTED_RISK" | "CANCELLED";
export type CarDependencyRisk = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type CarDependencyType = "INTERNAL" | "EXTERNAL" | "PROCUREMENT" | "FACILITY" | "RESOURCE" | "SUPPLIER" | "REGULATORY" | "OTHER";

export type CarControlHealth = {
  state: "HEALTHY" | "WATCH" | "AT_RISK" | "OVERDUE" | "CRITICAL" | "CLOSED";
  risk_score: number;
  factors: Array<{
    code: string;
    severity: string;
    message: string;
    milestone_key?: string;
    dependency_id?: string;
    due_date?: string;
    overdue_days?: number;
  }>;
  next_action: string;
  days_to_final_due: number | null;
};

export type CarControlMilestone = {
  id: string;
  milestone_key: string;
  phase_order: number;
  title: string;
  owner_user_id: string | null;
  original_due_date: string;
  current_due_date: string;
  status: CarControlMilestoneStatus;
  notes: string | null;
  evidence_ref: string | null;
  completed_by_user_id: string | null;
  completed_at: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CarControlDependency = {
  id: string;
  milestone_id: string | null;
  title: string;
  description: string | null;
  dependency_type: CarDependencyType;
  owner_user_id: string | null;
  due_date: string | null;
  risk_level: CarDependencyRisk;
  status: CarDependencyStatus;
  blocks_closure: boolean;
  mitigation_plan: string | null;
  created_at: string;
  updated_at: string;
};

export type CarDeadlineChange = {
  id: string;
  milestone_id: string | null;
  previous_due_date: string;
  requested_due_date: string;
  reason: string;
  impact_statement: string | null;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  requested_by_user_id: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

export type LegacyCarExtension = {
  id: string;
  requested_due_date: string;
  reason: string;
  status: string;
  requested_by_user_id: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

export type CarControlEvent = {
  id: string;
  milestone_id: string | null;
  event_key: string | null;
  event_type: string;
  severity: string;
  reason: string;
  snapshot: Record<string, unknown>;
  actor_user_id: string | null;
  system_generated: boolean;
  created_at: string;
};

export type CarControlLoop = {
  initialized: boolean;
  car: {
    id: string;
    car_number: string;
    title: string;
    summary: string;
    program: string;
    priority: string;
    status: string;
    assigned_to_user_id: string | null;
    due_date: string | null;
    target_closure_date: string | null;
    finding_id: string | null;
  };
  profile: {
    id: string;
    accountable_owner_user_id: string | null;
    original_due_date: string;
    current_due_date: string;
    effectiveness_required: boolean;
    initialized_from: string;
    created_at: string;
    updated_at: string;
  } | null;
  milestones: CarControlMilestone[];
  dependencies: CarControlDependency[];
  deadline_changes: CarDeadlineChange[];
  legacy_extension_history: LegacyCarExtension[];
  events: CarControlEvent[];
  health: CarControlHealth;
  closure_readiness: {
    ready: boolean;
    blockers: Array<{ code: string; message: string; milestone_key?: string; dependency_id?: string }>;
  };
  new_events_created?: number;
};

function jsonOptions(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function controlPath(amoCode: string, carId: string, suffix = ""): string {
  return qmsPath(amoCode, `/cars/${encodeURIComponent(carId)}/control-loop${suffix}`);
}

export function getCarControlLoop(amoCode: string, carId: string, signal?: AbortSignal): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId), { timeoutMs: 15_000, cacheTtlMs: 2_000, signal });
}

export function initializeCarControlLoop(
  amoCode: string,
  carId: string,
  payload: {
    accountable_owner_user_id?: string;
    final_due_date?: string;
    effectiveness_required: boolean;
    milestones?: Array<{ milestone_key: string; due_date?: string; owner_user_id?: string }>;
  },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, "/initialize"), jsonOptions("POST", payload));
}

export function updateCarControlProfile(
  amoCode: string,
  carId: string,
  payload: { accountable_owner_user_id?: string; effectiveness_required?: boolean },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, "/profile"), jsonOptions("PATCH", payload));
}

export function updateCarControlMilestone(
  amoCode: string,
  carId: string,
  milestoneId: string,
  payload: { owner_user_id?: string; status?: CarControlMilestoneStatus; notes?: string; evidence_ref?: string },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, `/milestones/${encodeURIComponent(milestoneId)}`), jsonOptions("PATCH", payload));
}

export function createCarDependency(
  amoCode: string,
  carId: string,
  payload: {
    milestone_id?: string;
    title: string;
    description?: string;
    dependency_type: CarDependencyType;
    owner_user_id?: string;
    due_date?: string;
    risk_level: CarDependencyRisk;
    blocks_closure: boolean;
    mitigation_plan?: string;
  },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, "/dependencies"), jsonOptions("POST", payload));
}

export function updateCarDependency(
  amoCode: string,
  carId: string,
  dependencyId: string,
  payload: Partial<{
    milestone_id: string;
    title: string;
    description: string;
    dependency_type: CarDependencyType;
    owner_user_id: string;
    due_date: string;
    risk_level: CarDependencyRisk;
    status: CarDependencyStatus;
    blocks_closure: boolean;
    mitigation_plan: string;
  }>,
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, `/dependencies/${encodeURIComponent(dependencyId)}`), jsonOptions("PATCH", payload));
}

export function requestCarDeadlineChange(
  amoCode: string,
  carId: string,
  payload: { milestone_id?: string; requested_due_date: string; reason: string; impact_statement?: string },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, "/deadline-changes"), jsonOptions("POST", payload));
}

export function decideCarDeadlineChange(
  amoCode: string,
  carId: string,
  changeId: string,
  payload: { decision: "APPROVE" | "REJECT"; review_note: string },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, `/deadline-changes/${encodeURIComponent(changeId)}/decision`), jsonOptions("POST", payload));
}

export function evaluateCarControlLoop(amoCode: string, carId: string): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, "/evaluate"), { method: "POST" });
}

export function closeCarControlLoop(
  amoCode: string,
  carId: string,
  payload: { evidence_ref?: string; closure_reason: string },
): Promise<CarControlLoop> {
  return apiRequest<CarControlLoop>(controlPath(amoCode, carId, "/close"), jsonOptions("POST", payload));
}
