import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type AircraftOption = {
  tailNumber: string;
  engineHours: number;
  engineCycles: number;
};

export async function listAircraftOptions(): Promise<AircraftOption[]> {
  return apiGet<AircraftOption[]>("/crs/aircraft/options", { headers: authHeaders() });
}

export async function fetchSerialNumber(): Promise<string> {
  const result = await apiGet<{ serial: string }>("/crs/serial/next", { headers: authHeaders() });
  return result.serial;
}

export async function submitCrsForm(payload: Record<string, unknown>) {
  return apiPost("/crs/", payload, { headers: authHeaders() });
}
