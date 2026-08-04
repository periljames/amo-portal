import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type PlanningStatus = "PLANNED" | "DUE_SOON" | "OVERDUE" | "COMPLETED" | "SUSPENDED";

export type ProgramItem = {
  id: number;
  template_code: string;
  task_code?: string | null;
  task_number?: string | null;
  title: string;
  ata_chapter?: string | null;
  status: string;
  interval_hours?: number | null;
  interval_cycles?: number | null;
  interval_days?: number | null;
};

export type DueListRow = {
  id: number;
  aircraft_serial_number: string;
  program_item_id: number;
  program_item?: {
    id: number;
    template_code: string;
    task_code?: string | null;
    task_number?: string | null;
    ata_chapter?: string | null;
    title: string;
  } | null;
  override_task_code?: string | null;
  override_title?: string | null;
  status: PlanningStatus;
  next_due_hours?: number | null;
  next_due_cycles?: number | null;
  next_due_date?: string | null;
  remaining_hours?: number | null;
  remaining_cycles?: number | null;
  remaining_days?: number | null;
};

export type DueList = {
  aircraft_serial_number: string;
  generated_at: string;
  due_now_count: number;
  due_soon_count: number;
  overdue_count: number;
  items: DueListRow[];
};

export type FleetPlanningSummary = {
  fleet_aircraft: number;
  utilisation_current: number;
  utilisation_stale: number;
  utilisation_missing: number;
  overdue: number;
  due_soon: number;
  planned: number;
  unbaselined: number;
  due_within_horizon: number;
};

export type FleetUtilisationRow = {
  aircraft_serial_number: string;
  registration: string;
  model?: string | null;
  current_hours?: number | null;
  current_cycles?: number | null;
  last_log_date?: string | null;
  days_since_log?: number | null;
  freshness_status: "CURRENT" | "STALE" | "MISSING";
  seven_day_daily_average_hours?: number | null;
  overdue_count: number;
  due_soon_count: number;
  next_due_date?: string | null;
  next_due_hours?: number | null;
  next_due_cycles?: number | null;
};

export type FleetDueItem = {
  api_id: number;
  aircraft_serial_number: string;
  registration: string;
  model?: string | null;
  program_item_id: number;
  task_code?: string | null;
  task_title: string;
  ata_chapter?: string | null;
  status: PlanningStatus;
  current_hours: number;
  current_cycles: number;
  last_log_date?: string | null;
  next_due_date?: string | null;
  next_due_hours?: number | null;
  next_due_cycles?: number | null;
  remaining_days?: number | null;
  remaining_hours?: number | null;
  remaining_cycles?: number | null;
  overdue_by_days?: number | null;
  overdue_by_hours?: number | null;
  overdue_by_cycles?: number | null;
  baseline_status: string;
};

export type FleetPlanningOverview = {
  generated_at: string;
  horizon_days: number;
  summary: FleetPlanningSummary;
  utilisation: FleetUtilisationRow[];
  due_items: FleetDueItem[];
};

export type FleetPlanningQuery = {
  horizonDays?: number;
  status?: PlanningStatus | "ALL";
  search?: string;
  limit?: number;
};

export const listProgramItems = (templateCode?: string) =>
  apiGet<ProgramItem[]>(
    `/maintenance-program/program-items/${templateCode ? `?template_code=${encodeURIComponent(templateCode)}` : ""}`,
    { headers: authHeaders() },
  );

export const getDueList = (aircraftSn: string) =>
  apiGet<DueList>(`/maintenance-program/aircraft/${encodeURIComponent(aircraftSn)}/due-list`, {
    headers: authHeaders(),
  });

export const recomputeDueList = (aircraftSn: string) =>
  apiPost<DueList>(
    `/maintenance-program/aircraft/${encodeURIComponent(aircraftSn)}/recompute-due`,
    {},
    { headers: authHeaders() },
  );

export const getFleetPlanningOverview = (query: FleetPlanningQuery = {}) => {
  const params = new URLSearchParams();
  params.set("horizon_days", String(query.horizonDays ?? 90));
  params.set("limit", String(query.limit ?? 1000));
  if (query.status && query.status !== "ALL") params.set("status_filter", query.status);
  if (query.search?.trim()) params.set("search", query.search.trim());
  return apiGet<FleetPlanningOverview>(`/maintenance-program/fleet/due-list?${params.toString()}`, {
    headers: authHeaders(),
  });
};
