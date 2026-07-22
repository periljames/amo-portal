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

type RosterAssignmentCreateInput = Omit<Roster.RosterAssignmentCreate, "status"> & {
  status?: Roster.RosterAssignmentCreate["status"] | string;
};

const ROSTER_ASSIGNMENT_STATUSES = new Set([
  "DRAFT",
  "PUBLISHED",
  "REST",
  "LEAVE",
  "TRAINING",
  "ON_CALL",
]);

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
  payload: RosterAssignmentCreateInput,
): Promise<Roster.RosterAssignmentRead> {
  const status = String(payload.status || "DRAFT").toUpperCase();
  if (!ROSTER_ASSIGNMENT_STATUSES.has(status)) {
    throw new Error(`Unsupported roster assignment status: ${status}`);
  }
  const idempotencyKey = payload.source_reference_id || newOfflineIdempotencyKey("roster-assignment");
  const normalized: Roster.RosterAssignmentCreate = {
    ...payload,
    status: status as Roster.RosterAssignmentCreate["status"],
    source_reference_id: idempotencyKey,
  };
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

export function exportRosterVersion(versionId: string, format: "csv" | "pdf" | "xlsx"): Promise<void> {
  return apiBlob(`/rostering/versions/${encodeURIComponent(versionId)}/export${queryString({ format })}`).then((blob) => {
    downloadBlob(blob, `roster-${versionId}.${format}`);
  });
}
