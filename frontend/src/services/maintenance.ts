import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import { listAircraft } from "./fleet";

export type NrStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "EXECUTED" | "CLOSED";
export type InspectionStatus = "REQUESTED" | "SCHEDULED" | "DONE" | "FAILED";
export type PartToolStatus = "REQUESTED" | "ISSUED" | "RETURNED" | "CANCELLED";

export interface NonRoutineItem { id: string; tail: string; woId: number; taskId?: number; description: string; dispositionRequired: boolean; dispositionText?: string; approver?: string; status: NrStatus; evidence: string[]; createdAt: string; }
export interface InspectionItem { id: string; woId: number; tail: string; inspectionType: string; requiredByRole: string; inspectorUserId?: string; status: InspectionStatus; findings: string; evidence: string[]; holdFlag: boolean; }
export interface PartToolRequest { id: string; woId: number; itemType: "Part"|"Tool"|"GSE"; description: string; qty: number; status: PartToolStatus; requestedBy: string; requestedAt: string; updatedAt: string; }
export interface MaintenanceSettings { woPrefix: string; nrApprovalRequired: boolean; inspectionsEnabled: boolean; evidenceRequiredToCloseTask: boolean; }

export interface DefectRead { id: number; aircraft_serial_number?: string; description: string; source: string; reported_by?: string; ata_chapter?: string; occurred_at: string; work_order_id?: number | null; task_card_id?: number | null; operator_event_id?: string | null; }

const STORAGE_KEYS = {
  nonRoutines: "maintenance.nonRoutines",
  inspections: "maintenance.inspections",
  parts: "maintenance.parts",
  settings: "maintenance.settings",
};

const defaultSettings: MaintenanceSettings = {
  woPrefix: "WO",
  nrApprovalRequired: true,
  inspectionsEnabled: true,
  evidenceRequiredToCloseTask: false,
};

function readLocal<T>(key: string, fallback: T): T {
  try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) as T : fallback; } catch { return fallback; }
}
function writeLocal<T>(key: string, value: T): void { localStorage.setItem(key, JSON.stringify(value)); }

export const getMaintenanceSettings = () => readLocal(STORAGE_KEYS.settings, defaultSettings);
export const saveMaintenanceSettings = (s: MaintenanceSettings) => writeLocal(STORAGE_KEYS.settings, s);

export const listNonRoutines = () => readLocal<NonRoutineItem[]>(STORAGE_KEYS.nonRoutines, []);
export const saveNonRoutine = (item: NonRoutineItem) => {
  const all = listNonRoutines();
  const idx = all.findIndex((x) => x.id === item.id);
  if (idx >= 0) all[idx] = item; else all.unshift(item);
  writeLocal(STORAGE_KEYS.nonRoutines, all);
};

export const listInspections = () => readLocal<InspectionItem[]>(STORAGE_KEYS.inspections, []);
export const saveInspection = (item: InspectionItem) => {
  const all = listInspections();
  const idx = all.findIndex((x) => x.id === item.id);
  if (idx >= 0) all[idx] = item; else all.unshift(item);
  writeLocal(STORAGE_KEYS.inspections, all);
};

export const listPartToolRequests = () => readLocal<PartToolRequest[]>(STORAGE_KEYS.parts, []);
export const savePartToolRequest = (item: PartToolRequest) => {
  const all = listPartToolRequests();
  const idx = all.findIndex((x) => x.id === item.id);
  if (idx >= 0) all[idx] = item; else all.unshift(item);
  writeLocal(STORAGE_KEYS.parts, all);
};

async function fetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBaseUrl()}${path}`, { headers: { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, credentials: "include" });
  if (res.status === 401) { handleAuthFailure("expired"); throw new Error("Session expired"); }
  if (!res.ok) throw new Error(await res.text());
  return await res.json() as T;
}

export async function listAllDefects(): Promise<DefectRead[]> {
  const aircraft = await listAircraft({ is_active: true });
  const rows = await Promise.all(aircraft.map(async (a) => {
    try { return await fetchJson<DefectRead[]>(`/aircraft/${encodeURIComponent(a.serial_number)}/defects`); } catch { return []; }
  }));
  return rows.flat().sort((a,b)=> new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime());
}
