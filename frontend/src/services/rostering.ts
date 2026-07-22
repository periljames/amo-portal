import { apiBlob, apiJson, downloadBlob, jsonBody, queryString } from "./typedApi";
import { newOfflineIdempotencyKey } from "./offlinePersistence";
import type * as Roster from "../types/rostering";

type DateRange = {
  from: string;
  to: string;
  base_station_id?: string | null;
  department_id?: string | null;
  user_id?: string | null;
};

type PeriodFilters = {
  status?: string | null;
  from?: string | null;
  to?: string | null;
};

type LifecycleRequest = {
  expected_state_revision?: number | null;
  idempotency_key?: string | null;
  comment?: string | null;
};

type DeleteAssignmentRequest = {
  reason: string;
  expected_state_revision?: number | null;
};

export function getRosterContracts(): Promise<Roster.RosterContractResponse> {
  return apiJson("/rostering/contracts", { offline: { cacheTtlMs: 15 * 60_000 } });
}

export function getRosterDashboard(range: DateRange): Promise<Roster.RosterDashboardResponse> {
  return apiJson(`/rostering/dashboard${queryString(range)}`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export function getPlanningBoard(range: DateRange): Promise<Roster.RosterPlanningBoardResponse> {
  return apiJson(`/rostering/planning-board${queryString(range)}`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export function getRosterPlanningBoard(
  from: string,
  to: string,
  baseStationId?: string,
): Promise<Roster.RosterPlanningBoardResponse> {
  return getPlanningBoard({ from, to, base_station_id: baseStationId || null });
}

export function listShiftTemplates(includeInactive = false): Promise<Roster.ShiftTemplateRead[]> {
  return apiJson(`/rostering/shift-templates${queryString({ include_inactive: includeInactive })}`, { offline: { cacheTtlMs: 15 * 60_000 } });
}

export function createShiftTemplate(payload: Roster.ShiftTemplateCreate): Promise<Roster.ShiftTemplateRead> {
  return apiJson("/rostering/shift-templates", { method: "POST", body: jsonBody(payload) });
}

export function updateShiftTemplate(
  templateId: string,
  payload: Partial<Roster.ShiftTemplateCreate>,
): Promise<Roster.ShiftTemplateRead> {
  return apiJson(`/rostering/shift-templates/${encodeURIComponent(templateId)}`, {
    method: "PATCH",
    body: jsonBody(payload),
  });
}

export function listRosterPeriods(filters?: string | PeriodFilters): Promise<Roster.RosterPeriodRead[]> {
  const normalized: PeriodFilters = typeof filters === "string" ? { status: filters } : (filters || {});
  return apiJson(`/rostering/periods${queryString(normalized)}`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export function createRosterPeriod(payload: Roster.RosterPeriodCreate): Promise<Roster.RosterPeriodRead> {
  return apiJson("/rostering/periods", { method: "POST", body: jsonBody(payload) });
}

export function updateRosterPeriod(
  periodId: string,
  payload: Partial<Roster.RosterPeriodCreate> & { status?: string },
): Promise<Roster.RosterPeriodRead> {
  return apiJson(`/rostering/periods/${encodeURIComponent(periodId)}`, {
    method: "PATCH",
    body: jsonBody(payload),
  });
}

export function getRosterPeriod(periodId: string): Promise<Roster.RosterPeriodRead> {
  return apiJson(`/rostering/periods/${encodeURIComponent(periodId)}`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export function listRosterVersions(periodId: string): Promise<Roster.RosterVersionRead[]> {
  return apiJson(`/rostering/periods/${encodeURIComponent(periodId)}/versions`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export function createRosterVersion(
  periodId: string,
  payload: Roster.RosterVersionCreate,
): Promise<Roster.RosterVersionRead> {
  return apiJson(`/rostering/periods/${encodeURIComponent(periodId)}/versions`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function amendPublishedRoster(
  versionId: string,
  payload: Roster.RosterVersionCreate,
): Promise<Roster.RosterVersionRead> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/amend`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function getRosterVersion(versionId: string): Promise<Roster.RosterVersionRead> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}`, { offline: { cacheTtlMs: 45_000 } });
}

export function listRosterAssignments(
  versionId: string,
  includeDeleted = false,
): Promise<Roster.RosterAssignmentRead[]> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/assignments${queryString({ include_deleted: includeDeleted })}`, { offline: { cacheTtlMs: 45_000 } });
}

export function createRosterAssignment(
  versionId: string,
  payload: Roster.RosterAssignmentCreate,
): Promise<Roster.RosterAssignmentRead> {
  const idempotencyKey = payload.source_reference_id || newOfflineIdempotencyKey("roster-assignment");
  const normalized = { ...payload, source_reference_id: idempotencyKey };
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/assignments`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: jsonBody(normalized),
    offline: {
      queueMutation: true,
      entityType: "roster-assignment",
      entityId: idempotencyKey,
      idempotencyKey,
    },
  });
}

export function updateRosterAssignment(
  assignmentId: string,
  payload: Roster.RosterAssignmentUpdate,
): Promise<Roster.RosterAssignmentRead> {
  const idempotencyKey = newOfflineIdempotencyKey("roster-update");
  return apiJson(`/rostering/assignments/${encodeURIComponent(assignmentId)}`, {
    method: "PATCH",
    headers: { "Idempotency-Key": idempotencyKey },
    body: jsonBody(payload),
    offline: {
      queueMutation: true,
      entityType: "roster-assignment",
      entityId: assignmentId,
      idempotencyKey,
    },
  });
}

export function deleteRosterAssignment(
  assignmentId: string,
  payload: DeleteAssignmentRequest,
): Promise<void> {
  const idempotencyKey = newOfflineIdempotencyKey("roster-delete");
  return apiJson(`/rostering/assignments/${encodeURIComponent(assignmentId)}`, {
    method: "DELETE",
    headers: { "Idempotency-Key": idempotencyKey },
    body: jsonBody(payload),
    offline: {
      queueMutation: true,
      entityType: "roster-assignment",
      entityId: assignmentId,
      idempotencyKey,
    },
  });
}

export function listRosterFindings(
  versionId: string,
  includeResolved = true,
): Promise<Roster.RosterValidationFindingRead[]> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/findings${queryString({ include_resolved: includeResolved })}`, { offline: { cacheTtlMs: 45_000 } });
}

export function validateRosterVersion(versionId: string): Promise<Roster.RosterValidationResult> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/validate`, { method: "POST" });
}

export function submitRosterVersion(
  versionId: string,
  payload: LifecycleRequest = {},
): Promise<Roster.RosterVersionRead> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/submit`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function approveRosterVersion(
  versionId: string,
  payload: LifecycleRequest = {},
): Promise<Roster.RosterVersionRead> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/approve`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function publishRosterVersion(
  versionId: string,
  payload: LifecycleRequest = {},
): Promise<Roster.RosterVersionRead> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/publish`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function acknowledgeRosterVersion(
  versionId: string,
  payload: string | { acknowledgement_note?: string | null; idempotency_key?: string | null } = {},
): Promise<{ id: string }> {
  const normalized = typeof payload === "string" ? { acknowledgement_note: payload } : payload;
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/acknowledge`, {
    method: "POST",
    body: jsonBody(normalized),
  });
}

export function getMyRoster(range: DateRange): Promise<Roster.MyRosterResponse>;
export function getMyRoster(from: string, to: string): Promise<Roster.MyRosterResponse>;
export function getMyRoster(rangeOrFrom: DateRange | string, to?: string): Promise<Roster.MyRosterResponse> {
  const range = typeof rangeOrFrom === "string" ? { from: rangeOrFrom, to: to || rangeOrFrom } : rangeOrFrom;
  return apiJson(`/rostering/my-roster${queryString(range)}`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export async function exportMyRosterCalendar(range: DateRange): Promise<void> {
  const result = await apiBlob(`/rostering/my-roster.ics${queryString(range)}`);
  downloadBlob(result.blob, result.filename || "my-duty-roster.ics");
}

export function listRosterRules(includeInactive = false): Promise<Roster.RosterRuleRead[]> {
  return apiJson(`/rostering/rules${queryString({ include_inactive: includeInactive })}`, { offline: { cacheTtlMs: 15 * 60_000 } });
}

export function createRosterRule(payload: Roster.RosterRuleCreate): Promise<Roster.RosterRuleRead> {
  return apiJson("/rostering/rules", { method: "POST", body: jsonBody(payload) });
}

export function updateRosterRule(
  ruleId: string,
  payload: Partial<Roster.RosterRuleCreate>,
): Promise<Roster.RosterRuleRead> {
  return apiJson(`/rostering/rules/${encodeURIComponent(ruleId)}`, {
    method: "PATCH",
    body: jsonBody(payload),
  });
}

export function getRosterReportSummary(range: DateRange): Promise<Roster.RosterReportSummary> {
  return apiJson(`/rostering/reports/summary${queryString(range)}`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export async function exportRosterReport(
  options: DateRange & { format: "csv" | "xlsx" | "pdf" | "ics" },
): Promise<void> {
  const result = await apiBlob(`/rostering/reports/export${queryString(options)}`);
  const extension = options.format;
  downloadBlob(result.blob, result.filename || `duty-roster-${options.from}-${options.to}.${extension}`);
}

export function listRosterTaskLinks(assignmentId: string): Promise<Roster.RosterTaskAssignmentLinkRead[]> {
  return apiJson(`/rostering/assignments/${encodeURIComponent(assignmentId)}/task-links`, { offline: { cacheTtlMs: 2 * 60_000 } });
}

export function linkRosterAssignmentToTaskAssignment(
  assignmentId: string,
  payload: {
    task_assignment_id: number;
    allocated_start?: string | null;
    allocated_end?: string | null;
    allocated_hours?: number | null;
  },
): Promise<Roster.RosterTaskAssignmentLinkRead> {
  return apiJson(`/rostering/assignments/${encodeURIComponent(assignmentId)}/task-links`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function allocateRosterAssignmentToTask(
  assignmentId: string,
  payload: {
    task_id: number;
    role_on_task?: string;
    task_assignment_status?: string;
    allocated_start?: string | null;
    allocated_end?: string | null;
    allocated_hours?: number | null;
  },
): Promise<Roster.RosterTaskAssignmentLinkRead> {
  return apiJson(`/rostering/assignments/${encodeURIComponent(assignmentId)}/task-allocations`, {
    method: "POST",
    body: jsonBody(payload),
  });
}
