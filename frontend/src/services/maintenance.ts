import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import { listAircraft } from "./fleet";
import { shouldUseMockData } from "./runtimeMode";

export type NrStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "EXECUTED" | "CLOSED";
export type InspectionStatus = "REQUESTED" | "SCHEDULED" | "DONE" | "FAILED";
export type PartToolStatus = "REQUESTED" | "ISSUED" | "RETURNED" | "CANCELLED";

export interface NonRoutineItem { id: string; tail: string; woId: number; taskId?: number; description: string; dispositionRequired: boolean; dispositionText?: string; approver?: string; status: NrStatus; evidence: string[]; createdAt: string; }
export interface InspectionItem { id: string; woId: number; tail: string; inspectionType: string; requiredByRole: string; inspectorUserId?: string; status: InspectionStatus; findings: string; evidence: string[]; holdFlag: boolean; }
export interface PartToolRequest { id: string; woId: number; itemType: "Part"|"Tool"|"GSE"; description: string; qty: number; status: PartToolStatus; requestedBy: string; requestedAt: string; updatedAt: string; }
export interface MaintenanceSettings { woPrefix: string; nrApprovalRequired: boolean; inspectionsEnabled: boolean; evidenceRequiredToCloseTask: boolean; }
export interface DefectRead { id: number; aircraft_serial_number?: string; description: string; source: string; reported_by?: string; ata_chapter?: string; occurred_at: string; work_order_id?: number | null; task_card_id?: number | null; operator_event_id?: string | null; }

const STORAGE_KEYS = { nonRoutines: "maintenance.nonRoutines", inspections: "maintenance.inspections", parts: "maintenance.parts", settings: "maintenance.settings", seeded: "maintenance.demoSeeded" };

const defaultSettings: MaintenanceSettings = { woPrefix: "WO", nrApprovalRequired: true, inspectionsEnabled: true, evidenceRequiredToCloseTask: false };
const demoNow = new Date().toISOString();
const demoNR: NonRoutineItem[] = [{ id: "nr-demo-001", tail: "DEMO-001", woId: 2, taskId: 22, description: "Corrosion finding at RH flap bracket", dispositionRequired: true, status: "SUBMITTED", evidence: [], createdAt: demoNow }];
const demoInspections: InspectionItem[] = [{ id: "insp-demo-001", woId: 3, tail: "DEMO-001", inspectionType: "Independent inspection", requiredByRole: "QUALITY", status: "REQUESTED", findings: "Awaiting inspector assignment", evidence: [], holdFlag: true }];
const demoParts: PartToolRequest[] = [{ id: "pt-demo-001", woId: 2, itemType: "Part", description: "Hydraulic seal kit", qty: 2, status: "REQUESTED", requestedBy: "demo.tech", requestedAt: demoNow, updatedAt: demoNow }];

function readLocal<T>(key: string, fallback: T): T { try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) as T : fallback; } catch { return fallback; } }
function writeLocal<T>(key: string, value: T): void { localStorage.setItem(key, JSON.stringify(value)); }

export function seedMaintenanceDemoData(): void {
  if (!shouldUseMockData()) return;
  const seeded = localStorage.getItem(STORAGE_KEYS.seeded) === "1";
  if (seeded) return;
  writeLocal(STORAGE_KEYS.nonRoutines, demoNR);
  writeLocal(STORAGE_KEYS.inspections, demoInspections);
  writeLocal(STORAGE_KEYS.parts, demoParts);
  localStorage.setItem(STORAGE_KEYS.seeded, "1");
}

function canEditLocal(): boolean { return shouldUseMockData(); }

export const getMaintenanceSettings = () => readLocal(STORAGE_KEYS.settings, defaultSettings);
export const saveMaintenanceSettings = (s: MaintenanceSettings) => writeLocal(STORAGE_KEYS.settings, s);

export const listNonRoutines = () => { seedMaintenanceDemoData(); return shouldUseMockData() ? readLocal<NonRoutineItem[]>(STORAGE_KEYS.nonRoutines, demoNR) : []; };
export const saveNonRoutine = (item: NonRoutineItem) => {
  if (!canEditLocal()) return false;
  const all = listNonRoutines(); const idx = all.findIndex((x) => x.id === item.id); if (idx >= 0) all[idx] = item; else all.unshift(item); writeLocal(STORAGE_KEYS.nonRoutines, all); return true;
};

export const listInspections = () => { seedMaintenanceDemoData(); return shouldUseMockData() ? readLocal<InspectionItem[]>(STORAGE_KEYS.inspections, demoInspections) : []; };
export const saveInspection = (item: InspectionItem) => {
  if (!canEditLocal()) return false;
  const all = listInspections(); const idx = all.findIndex((x) => x.id === item.id); if (idx >= 0) all[idx] = item; else all.unshift(item); writeLocal(STORAGE_KEYS.inspections, all); return true;
};

export const listPartToolRequests = () => { seedMaintenanceDemoData(); return shouldUseMockData() ? readLocal<PartToolRequest[]>(STORAGE_KEYS.parts, demoParts) : []; };
export const savePartToolRequest = (item: PartToolRequest) => {
  if (!canEditLocal()) return false;
  const all = listPartToolRequests(); const idx = all.findIndex((x) => x.id === item.id); if (idx >= 0) all[idx] = item; else all.unshift(item); writeLocal(STORAGE_KEYS.parts, all); return true;
};

async function fetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBaseUrl()}${path}`, { headers: { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, credentials: "include" });
  if (res.status === 401) { handleAuthFailure("expired"); throw new Error("Session expired"); }
  if (!res.ok) throw new Error(await res.text());
  return await res.json() as T;
}

export async function listAllDefects(): Promise<DefectRead[]> {
  if (!shouldUseMockData()) {
    const aircraft = await listAircraft({ is_active: true });
    const rows = await Promise.all(aircraft.map(async (a) => { try { return await fetchJson<DefectRead[]>(`/aircraft/${encodeURIComponent(a.serial_number)}/defects`); } catch { return []; } }));
    return rows.flat().sort((a,b)=> new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime());
  }
  return [{ id: 9001, aircraft_serial_number: "DEMO-001", description: "Hydraulic seep observed", source: "MAINTENANCE", ata_chapter: "29", occurred_at: demoNow, work_order_id: 2, operator_event_id: "DEF-DEMO-9001" }];
}
