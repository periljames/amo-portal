import { getToken, handleAuthFailure } from "./auth";
import { portalFetch } from "./offlineHttp";

export type DailyTargetType = "AIRFRAME" | "ENGINE" | "PROPELLER" | "APU" | "COMPONENT";
export type DailyDerivation = "SHARED_DAILY" | "ZERO_DEFAULT" | "OVERRIDE";

export interface DailyExposure {
  target_type: DailyTargetType;
  component_id: number | null;
  component_position: string;
  component_description: string | null;
  derivation: DailyDerivation;
  hours_delta: string;
  cycles_delta: number;
  before_hours: string | null;
  before_cycles: number | null;
  after_hours: string | null;
  after_cycles: number | null;
  baseline_missing: boolean;
  override_reason: string | null;
}

export interface DailyUtilisationContext {
  aircraft_serial_number: string;
  registration: string;
  model: string | null;
  current_hours: string | null;
  current_cycles: number | null;
  last_posted_date: string | null;
  installed_components: DailyExposure[];
}

export interface DailyComponentOverride {
  component_id: number;
  hours_delta?: string | null;
  cycles_delta?: number | null;
  reason: string;
}

export interface DailyUtilisationPayload {
  operation_date: string;
  techlog_no: string;
  station?: string | null;
  flight_hours: string;
  cycles: number;
  nil_operation: boolean;
  source_reference?: string | null;
  remarks?: string | null;
  idempotency_key: string;
  component_overrides: DailyComponentOverride[];
}

export interface DailyUtilisationPreview {
  aircraft_serial_number: string;
  registration: string;
  operation_date: string;
  flight_hours: string;
  cycles: number;
  can_post: boolean;
  blockers: string[];
  exposures: DailyExposure[];
}

export interface DailyUtilisationEntry {
  id: string;
  aircraft_serial_number: string;
  operation_date: string;
  techlog_no: string;
  station: string | null;
  flight_hours: string;
  cycles: number;
  nil_operation: boolean;
  status: string;
  remarks: string | null;
  created_at: string;
  posted_at: string | null;
}

export interface DailyUtilisationDraft {
  entry: DailyUtilisationEntry;
  preview: DailyUtilisationPreview;
}

export interface DailyUtilisationPostResult {
  entry: DailyUtilisationEntry;
  aircraft_total_hours: string;
  aircraft_total_cycles: number;
  component_updates: number;
}

function headers(): Headers {
  const result = new Headers({ Accept: "application/json", "Content-Type": "application/json" });
  const token = getToken();
  if (token) result.set("Authorization", `Bearer ${token}`);
  return result;
}

async function parseError(response: Response): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
  const detail = payload?.detail;
  if (typeof detail === "string") return new Error(detail);
  if (detail && typeof detail === "object" && "message" in detail) {
    const value = detail as { message?: string; blockers?: string[] };
    return new Error([value.message, ...(value.blockers ?? [])].filter(Boolean).join(" — "));
  }
  return new Error(`Daily utilisation API ${response.status}: ${response.statusText}`);
}

async function request<T>(path: string, method: "GET" | "POST", body?: unknown): Promise<T> {
  const response = await portalFetch(path, {
    method,
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "include",
    offline: { cache: method === "GET", queueMutation: false },
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw await parseError(response);
  return await response.json() as T;
}

export function getDailyUtilisationContext(serialNumber: string): Promise<DailyUtilisationContext> {
  return request(`/architecture/daily-utilisation/aircraft/${encodeURIComponent(serialNumber)}/context`, "GET");
}

export function listDailyUtilisationEntries(serialNumber: string): Promise<DailyUtilisationEntry[]> {
  return request(`/architecture/daily-utilisation/aircraft/${encodeURIComponent(serialNumber)}/entries`, "GET");
}

export function previewDailyUtilisation(
  serialNumber: string,
  payload: DailyUtilisationPayload,
): Promise<DailyUtilisationPreview> {
  return request(
    `/architecture/daily-utilisation/aircraft/${encodeURIComponent(serialNumber)}/preview`,
    "POST",
    payload,
  );
}

export function createDailyUtilisationDraft(
  serialNumber: string,
  payload: DailyUtilisationPayload,
): Promise<DailyUtilisationDraft> {
  return request(
    `/architecture/daily-utilisation/aircraft/${encodeURIComponent(serialNumber)}/entries`,
    "POST",
    payload,
  );
}

export function postDailyUtilisation(entryId: string): Promise<DailyUtilisationPostResult> {
  return request(`/architecture/daily-utilisation/entries/${encodeURIComponent(entryId)}/post`, "POST", {});
}
