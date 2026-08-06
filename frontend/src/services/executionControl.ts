import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type ExecutionEvent = {
  id: string;
  session_id: string;
  work_order_id?: number | null;
  task_card_id?: number | null;
  event_type: string;
  from_status?: string | null;
  to_status?: string | null;
  payload_json: Record<string, unknown>;
  occurred_at: string;
};

export type TaskIssue = {
  id: string;
  session_id: string;
  work_order_id: number;
  task_card_id?: number | null;
  category: string;
  severity: string;
  title: string;
  description: string;
  status: string;
  disposition?: string | null;
  linked_non_routine_task_id?: number | null;
  evidence_json: string[];
  raised_at: string;
  resolved_at?: string | null;
  resolution_notes?: string | null;
};

export type ExecutionSession = {
  id: string;
  work_package_id: number;
  work_order_id?: number | null;
  package_freeze_id: string;
  shift_reference?: string | null;
  station?: string | null;
  status: string;
  started_at: string;
  closed_at?: string | null;
  closure_notes?: string | null;
  events: ExecutionEvent[];
  issues: TaskIssue[];
};

export type HandbackFinding = {
  id: string;
  handback_id: string;
  category: string;
  severity: string;
  description: string;
  status: string;
  response_notes?: string | null;
  raised_at: string;
  resolved_at?: string | null;
};

export type Handback = {
  id: string;
  work_package_id: number;
  package_freeze_id: string;
  version: number;
  status: string;
  manifest_hash: string;
  manifest_json: Record<string, unknown>;
  readiness_json: { status?: string; blockers?: string[]; warnings?: string[]; metrics?: Record<string, unknown> };
  submitted_at?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  accepted_at?: string | null;
  created_at: string;
  updated_at: string;
  findings: HandbackFinding[];
  events: Array<{ id: string; event_type: string; from_status?: string | null; to_status: string; notes?: string | null; created_at: string }>;
};

export type ExecutionDashboard = {
  open_sessions: number;
  blocked_sessions: number;
  open_issues: number;
  critical_issues: number;
  draft_handbacks: number;
  submitted_handbacks: number;
  rejected_handbacks: number;
  accepted_handbacks: number;
};

const base = "/work-packages/execution-control";

export function getExecutionDashboard() {
  return apiGet<ExecutionDashboard>(`${base}/dashboard`, { headers: authHeaders() });
}

export function listExecutionSessions(packageId?: number) {
  const params = packageId ? `?package_id=${packageId}` : "";
  return apiGet<ExecutionSession[]>(`${base}/sessions${params}`, { headers: authHeaders() });
}

export function startExecutionSession(payload: {
  work_package_id: number;
  work_order_id?: number;
  shift_reference?: string;
  station?: string;
}) {
  return apiPost<ExecutionSession>(`${base}/sessions`, payload, { headers: authHeaders() });
}

export function recordExecutionEvent(sessionId: string, payload: {
  work_order_id?: number;
  task_card_id?: number;
  event_type: string;
  to_status?: string;
  payload_json?: Record<string, unknown>;
}) {
  return apiPost<ExecutionEvent>(`${base}/sessions/${encodeURIComponent(sessionId)}/events`, payload, { headers: authHeaders() });
}

export function raiseTaskIssue(sessionId: string, payload: {
  work_order_id: number;
  task_card_id?: number;
  category: string;
  severity: string;
  title: string;
  description: string;
  evidence_json?: string[];
}) {
  return apiPost<TaskIssue>(`${base}/sessions/${encodeURIComponent(sessionId)}/issues`, payload, { headers: authHeaders() });
}

export function resolveTaskIssue(issueId: string, disposition: string, resolutionNotes: string, nonRoutineTaskId?: number) {
  return apiPost<TaskIssue>(`${base}/issues/${encodeURIComponent(issueId)}/resolve`, {
    disposition,
    resolution_notes: resolutionNotes,
    linked_non_routine_task_id: nonRoutineTaskId,
  }, { headers: authHeaders() });
}

export function closeExecutionSession(sessionId: string, closureNotes: string) {
  return apiPost<ExecutionSession>(`${base}/sessions/${encodeURIComponent(sessionId)}/close`, { closure_notes: closureNotes }, { headers: authHeaders() });
}

export function listHandbacks(packageId?: number) {
  const params = packageId ? `?package_id=${packageId}` : "";
  return apiGet<Handback[]>(`${base}/handbacks${params}`, { headers: authHeaders() });
}

export function buildHandback(packageId: number) {
  return apiPost<Handback>(`${base}/handbacks/build`, { work_package_id: packageId }, { headers: authHeaders() });
}

export function submitHandback(handbackId: string, notes: string) {
  return apiPost<Handback>(`${base}/handbacks/${encodeURIComponent(handbackId)}/submit`, { submission_notes: notes }, { headers: authHeaders() });
}

export function addHandbackFinding(handbackId: string, payload: { category: string; severity: string; description: string }) {
  return apiPost<HandbackFinding>(`${base}/handbacks/${encodeURIComponent(handbackId)}/findings`, payload, { headers: authHeaders() });
}

export function resolveHandbackFinding(findingId: string, responseNotes: string) {
  return apiPost<HandbackFinding>(`${base}/findings/${encodeURIComponent(findingId)}/resolve`, { response_notes: responseNotes }, { headers: authHeaders() });
}

export function reviewHandback(handbackId: string, decision: "ACCEPT" | "REJECT", reviewNotes: string) {
  return apiPost<Handback>(`${base}/handbacks/${encodeURIComponent(handbackId)}/review`, { decision, review_notes: reviewNotes }, { headers: authHeaders() });
}
