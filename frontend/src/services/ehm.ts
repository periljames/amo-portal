// src/services/ehm.ts
import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";

const API_BASE = getApiBaseUrl();

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

export type EhmLog = {
  id: string;
  aircraft_serial_number: string | null;
  engine_position: string;
  engine_serial_number: string | null;
  source: string | null;
  notes: string | null;
  original_filename: string | null;
  content_type: string | null;
  storage_path: string;
  size_bytes: number;
  sha256_hash: string;
  parse_status: string;
  parse_error: string | null;
  parsed_at: string | null;
  parsed_record_count: number;
  created_at: string;
};

export async function listEhmLogs(params?: {
  aircraft_serial_number?: string;
  engine_position?: string;
  parse_status?: string;
  limit?: number;
  offset?: number;
}): Promise<EhmLog[]> {
  const query = toQuery(params ?? {});
  return fetchJson<EhmLog[]>(`/reliability/ehm/logs${query}`);
}

export async function previewEhmLog(file: File): Promise<{
  aircraft_serial_number?: string | null;
  engine_position?: string | null;
  engine_serial_number?: string | null;
  decode_offset?: number | null;
}> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/reliability/ehm/logs/preview`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: form,
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Preview failed (${res.status})`);
  }
  return (await res.json()) as {
    aircraft_serial_number?: string | null;
    engine_position?: string | null;
    engine_serial_number?: string | null;
    decode_offset?: number | null;
  };
}

export async function uploadEhmLog(payload: {
  file: File;
  aircraft_serial_number: string;
  engine_position: string;
  engine_serial_number?: string | null;
  source?: string | null;
  notes?: string | null;
}): Promise<EhmLog> {
  const token = getToken();
  const form = new FormData();
  form.append("file", payload.file);
  form.append("aircraft_serial_number", payload.aircraft_serial_number);
  form.append("engine_position", payload.engine_position);
  if (payload.engine_serial_number) {
    form.append("engine_serial_number", payload.engine_serial_number);
  }
  if (payload.source) {
    form.append("source", payload.source);
  }
  if (payload.notes) {
    form.append("notes", payload.notes);
  }

  const res = await fetch(`${API_BASE}/reliability/ehm/logs/upload`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: form,
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Upload failed (${res.status})`);
  }
  const data = (await res.json()) as { log: EhmLog };
  return data.log;
}

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
