// src/services/rostering.ts
import { authHeaders } from "./auth";
import { apiGet, apiPost, apiPut } from "./crs";
import type {
  MyRosterResponse,
  RosterAssignmentCreate,
  RosterAssignmentRead,
  RosterContractResponse,
  RosterPeriodCreate,
  RosterPeriodRead,
  RosterPlanningBoardResponse,
  RosterTaskAssignmentLinkRead,
  RosterValidationResult,
  RosterVersionCreate,
  RosterVersionRead,
  ShiftTemplateCreate,
  ShiftTemplateRead,
} from "../types/rostering";

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") sp.set(key, String(value));
  });
  const rendered = sp.toString();
  return rendered ? `?${rendered}` : "";
}

export function getRosterContracts(): Promise<RosterContractResponse> {
  return apiGet<RosterContractResponse>("/rostering/contracts", { headers: authHeaders() });
}

export function listShiftTemplates(includeInactive = false): Promise<ShiftTemplateRead[]> {
  return apiGet<ShiftTemplateRead[]>(`/rostering/shift-templates${qs({ include_inactive: includeInactive })}`, { headers: authHeaders() });
}

export function createShiftTemplate(payload: ShiftTemplateCreate): Promise<ShiftTemplateRead> {
  return apiPost<ShiftTemplateRead>("/rostering/shift-templates", payload, { headers: authHeaders() });
}

export function updateShiftTemplate(templateId: string, payload: Partial<ShiftTemplateCreate>): Promise<ShiftTemplateRead> {
  return apiPut<ShiftTemplateRead>(`/rostering/shift-templates/${encodeURIComponent(templateId)}`, payload, { headers: authHeaders() });
}

export function listRosterPeriods(status?: string): Promise<RosterPeriodRead[]> {
  return apiGet<RosterPeriodRead[]>(`/rostering/periods${qs({ status })}`, { headers: authHeaders() });
}

export function createRosterPeriod(payload: RosterPeriodCreate): Promise<RosterPeriodRead> {
  return apiPost<RosterPeriodRead>("/rostering/periods", payload, { headers: authHeaders() });
}

export function updateRosterPeriod(periodId: string, payload: Partial<RosterPeriodCreate> & { status?: string }): Promise<RosterPeriodRead> {
  return apiPut<RosterPeriodRead>(`/rostering/periods/${encodeURIComponent(periodId)}`, payload, { headers: authHeaders() });
}

export function listRosterVersions(periodId: string): Promise<RosterVersionRead[]> {
  return apiGet<RosterVersionRead[]>(`/rostering/periods/${encodeURIComponent(periodId)}/versions`, { headers: authHeaders() });
}

export function createRosterVersion(periodId: string, payload: RosterVersionCreate): Promise<RosterVersionRead> {
  return apiPost<RosterVersionRead>(`/rostering/periods/${encodeURIComponent(periodId)}/versions`, payload, { headers: authHeaders() });
}

export function listRosterAssignments(versionId: string): Promise<RosterAssignmentRead[]> {
  return apiGet<RosterAssignmentRead[]>(`/rostering/versions/${encodeURIComponent(versionId)}/assignments`, { headers: authHeaders() });
}

export function createRosterAssignment(versionId: string, payload: RosterAssignmentCreate): Promise<RosterAssignmentRead> {
  return apiPost<RosterAssignmentRead>(`/rostering/versions/${encodeURIComponent(versionId)}/assignments`, payload, { headers: authHeaders() });
}

export function updateRosterAssignment(assignmentId: string, payload: Partial<RosterAssignmentCreate>): Promise<RosterAssignmentRead> {
  return apiPut<RosterAssignmentRead>(`/rostering/assignments/${encodeURIComponent(assignmentId)}`, payload, { headers: authHeaders() });
}

export function validateRosterVersion(versionId: string): Promise<RosterValidationResult> {
  return apiPost<RosterValidationResult>(`/rostering/versions/${encodeURIComponent(versionId)}/validate`, undefined, { headers: authHeaders() });
}

export function submitRosterVersion(versionId: string): Promise<RosterVersionRead> {
  return apiPost<RosterVersionRead>(`/rostering/versions/${encodeURIComponent(versionId)}/submit`, undefined, { headers: authHeaders() });
}

export function approveRosterVersion(versionId: string): Promise<RosterVersionRead> {
  return apiPost<RosterVersionRead>(`/rostering/versions/${encodeURIComponent(versionId)}/approve`, undefined, { headers: authHeaders() });
}

export function publishRosterVersion(versionId: string): Promise<RosterVersionRead> {
  return apiPost<RosterVersionRead>(`/rostering/versions/${encodeURIComponent(versionId)}/publish`, undefined, { headers: authHeaders() });
}

export function acknowledgeRosterVersion(versionId: string, acknowledgement_note?: string): Promise<{ id: string }> {
  return apiPost<{ id: string }>(`/rostering/versions/${encodeURIComponent(versionId)}/acknowledge`, { acknowledgement_note }, { headers: authHeaders() });
}

export function getMyRoster(from: string, to: string): Promise<MyRosterResponse> {
  return apiGet<MyRosterResponse>(`/rostering/my-roster${qs({ from, to })}`, { headers: authHeaders() });
}

export function getRosterPlanningBoard(from: string, to: string, baseStationId?: string): Promise<RosterPlanningBoardResponse> {
  return apiGet<RosterPlanningBoardResponse>(`/rostering/planning-board${qs({ from, to, base_station_id: baseStationId })}`, { headers: authHeaders() });
}


export function listRosterTaskLinks(assignmentId: string): Promise<RosterTaskAssignmentLinkRead[]> {
  return apiGet<RosterTaskAssignmentLinkRead[]>(`/rostering/assignments/${encodeURIComponent(assignmentId)}/task-links`, { headers: authHeaders() });
}

export function linkRosterAssignmentToTaskAssignment(
  assignmentId: string,
  payload: { task_assignment_id: number; allocated_start?: string | null; allocated_end?: string | null; allocated_hours?: number | null },
): Promise<RosterTaskAssignmentLinkRead> {
  return apiPost<RosterTaskAssignmentLinkRead>(`/rostering/assignments/${encodeURIComponent(assignmentId)}/task-links`, payload, { headers: authHeaders() });
}

export function allocateRosterAssignmentToTask(
  assignmentId: string,
  payload: { task_id: number; role_on_task?: string; task_assignment_status?: string; allocated_start?: string | null; allocated_end?: string | null; allocated_hours?: number | null },
): Promise<RosterTaskAssignmentLinkRead> {
  return apiPost<RosterTaskAssignmentLinkRead>(`/rostering/assignments/${encodeURIComponent(assignmentId)}/task-allocations`, payload, { headers: authHeaders() });
}
