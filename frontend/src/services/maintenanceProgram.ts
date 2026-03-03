import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

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
  api_id: number;
  aircraft_serial_number: string;
  title: string;
  task_code?: string | null;
  status: string;
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

export const listProgramItems = (templateCode?: string) =>
  apiGet<ProgramItem[]>(`/maintenance-program/program-items/${templateCode ? `?template_code=${encodeURIComponent(templateCode)}` : ""}`, { headers: authHeaders() });

export const getDueList = (aircraftSn: string) =>
  apiGet<DueList>(`/maintenance-program/aircraft/${encodeURIComponent(aircraftSn)}/due-list`, { headers: authHeaders() });

export const recomputeDueList = (aircraftSn: string) =>
  apiPost<DueList>(`/maintenance-program/aircraft/${encodeURIComponent(aircraftSn)}/recompute-due`, {}, { headers: authHeaders() });
