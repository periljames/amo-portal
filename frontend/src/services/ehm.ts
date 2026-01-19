// src/services/ehm.ts
import { getToken, handleAuthFailure } from "./auth";

const API_BASE =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type QueryVal = string | number | boolean | null | undefined;

function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === null || v === undefined) return;
    qs.set(k, String(v));
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function fetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
  }
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export type EngineTrendStatus = {
  id: number;
  amo_id: string;
  aircraft_serial_number: string;
  engine_position: string;
  engine_serial_number: string | null;
  last_upload_date: string | null;
  last_trend_date: string | null;
  last_review_date: string | null;
  previous_status: string | null;
  current_status: string | null;
};

export type EngineTrendPoint = {
  date: string;
  raw: number | null;
  corrected: number | null;
  delta: number | null;
  status: string | null;
};

export type EngineTrendEvent = {
  date: string;
  event_type: string;
  reference_code?: string | null;
  severity?: string | null;
  description?: string | null;
};

export type EngineTrendSeries = {
  metric: string;
  baseline: number | null;
  control_limit: number | null;
  method: string | null;
  parameters?: Record<string, any> | null;
  points: EngineTrendPoint[];
  events: EngineTrendEvent[];
};

export type EngineSnapshot = {
  id: number;
  amo_id: string;
  aircraft_serial_number: string;
  engine_position: string;
  engine_serial_number?: string | null;
  flight_date: string;
  flight_leg?: string | null;
  data_source?: string | null;
};

export async function listEngineTrendStatus(): Promise<EngineTrendStatus[]> {
  return fetchJson<EngineTrendStatus[]>("/reliability/engine-trends/fleet-status");
}

export async function getEngineTrendSeries(params: {
  aircraft_serial_number: string;
  engine_position: string;
  metric: string;
  engine_serial_number?: string | null;
  baseline_window?: number;
  shift_threshold?: number;
}): Promise<EngineTrendSeries> {
  const query = toQuery(params);
  return fetchJson<EngineTrendSeries>(`/reliability/engine-trends/series${query}`);
}

export async function listEngineSnapshots(): Promise<EngineSnapshot[]> {
  return fetchJson<EngineSnapshot[]>("/reliability/engine-snapshots");
}
