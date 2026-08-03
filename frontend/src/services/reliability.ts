// src/services/reliability.ts
import { getToken, handleAuthFailure, markSessionActivity } from "./auth";
import { getApiBaseUrl } from "./config";
import { apiRequest } from "./apiClient";
import { downloadWithXhr, type DownloadedFile } from "../utils/downloads";

const API_BASE = getApiBaseUrl();
const REPORTS_CACHE_TTL_MS = 8000;

let reportsCache: { data: ReliabilityReportRead[]; expiresAt: number } | null = null;

export type ReliabilityReportStatus = "PENDING" | "READY" | "FAILED";

export type ReliabilityReportRead = {
  id: number;
  amo_id: string;
  window_start: string;
  window_end: string;
  status: ReliabilityReportStatus;
  file_ref?: string | null;
  created_at: string;
  created_by_user_id?: string | null;
};

export type TransferProgress = {
  loadedBytes: number;
  totalBytes?: number;
  percent?: number;
  megaBytesPerSecond: number;
  megaBitsPerSecond: number;
};

function buildAuthHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function buildSpeed(
  loadedBytes: number,
  totalBytes: number | undefined,
  startedAt: number
): TransferProgress {
  const elapsedSeconds = Math.max((performance.now() - startedAt) / 1000, 0.001);
  const megaBytesPerSecond = loadedBytes / (1024 * 1024) / elapsedSeconds;
  const megaBitsPerSecond = megaBytesPerSecond * 8;
  const percent = totalBytes ? Math.min((loadedBytes / totalBytes) * 100, 100) : undefined;
  return {
    loadedBytes,
    totalBytes,
    percent,
    megaBytesPerSecond,
    megaBitsPerSecond,
  };
}

export async function createReliabilityReport(
  windowStart: string,
  windowEnd: string
): Promise<ReliabilityReportRead> {
  const token = getToken();
  markSessionActivity("reliability-report-create");
  const res = await fetch(`${API_BASE}/reliability/reports`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
    body: JSON.stringify({
      window_start: windowStart,
      window_end: windowEnd,
    }),
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  reportsCache = null;
  return (await res.json()) as ReliabilityReportRead;
}

export async function listReliabilityReports(options?: { force?: boolean }): Promise<ReliabilityReportRead[]> {
  if (!options?.force && reportsCache && reportsCache.expiresAt > Date.now()) {
    return reportsCache.data;
  }
  const token = getToken();
  markSessionActivity("reliability-report-list");
  const res = await fetch(`${API_BASE}/reliability/reports`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  const data = (await res.json()) as ReliabilityReportRead[];
  reportsCache = {
    data,
    expiresAt: Date.now() + REPORTS_CACHE_TTL_MS,
  };
  return data;
}

export async function downloadReliabilityReport(
  reportId: number,
  onProgress?: (progress: TransferProgress) => void
): Promise<DownloadedFile> {
  const startedAt = performance.now();
  markSessionActivity("reliability-report-download");
  return downloadWithXhr({
    url: `${API_BASE}/reliability/reports/${reportId}/download`,
    headers: buildAuthHeader(),
    fallbackFilename: `reliability-report-${reportId}.pdf`,
    onProgress: onProgress
      ? (loaded, total) => {
          markSessionActivity("reliability-report-download-progress");
          onProgress(buildSpeed(loaded, total, startedAt));
        }
      : undefined,
    retries: 3,
  });
}

export async function downloadFracasEvidencePack(caseId: number): Promise<DownloadedFile> {
  markSessionActivity("fracas-export");
  return downloadWithXhr({
    url: `${API_BASE}/reliability/fracas/cases/${caseId}/evidence-pack`,
    headers: buildAuthHeader(),
    fallbackFilename: `fracas-${caseId}-evidence-pack.zip`,
    retries: 3,
  });
}

export type ReliabilitySeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ReliabilityEventType = "DEFECT" | "REMOVAL" | "INSTALLATION" | "OCTM" | "ECTM" | "FRACAS" | "OTHER";
export type ReliabilityAlertStatus = "OPEN" | "ACKNOWLEDGED" | "CLOSED";
export type FracasStatus = "OPEN" | "IN_ANALYSIS" | "ACTIONS" | "MONITORING" | "CLOSED";
export type EngineTrendStatus = "Trend Normal" | "Trend Shift";

export type ReliabilityEvent = {
  id: number;
  amo_id: string;
  aircraft_serial_number?: string | null;
  engine_position?: string | null;
  component_id?: number | null;
  work_order_id?: number | null;
  task_card_id?: number | null;
  event_type: ReliabilityEventType;
  severity?: ReliabilitySeverity | null;
  ata_chapter?: string | null;
  reference_code?: string | null;
  source_system?: string | null;
  description?: string | null;
  operator_event_id?: string | null;
  occurred_at: string;
  created_at: string;
};

export type ReliabilityAlert = {
  id: number;
  amo_id: string;
  kpi_id?: number | null;
  threshold_set_id?: number | null;
  alert_code: string;
  status: ReliabilityAlertStatus;
  severity: ReliabilitySeverity;
  message?: string | null;
  triggered_at: string;
  resolved_at?: string | null;
  acknowledged_at?: string | null;
  created_at: string;
};

export type FracasCase = {
  id: number;
  amo_id: string;
  title: string;
  description?: string | null;
  status: FracasStatus;
  severity?: ReliabilitySeverity | null;
  classification?: string | null;
  aircraft_serial_number?: string | null;
  engine_position?: string | null;
  component_id?: number | null;
  work_order_id?: number | null;
  task_card_id?: number | null;
  reliability_event_id?: number | null;
  opened_at: string;
  closed_at?: string | null;
  root_cause?: string | null;
  corrective_action_summary?: string | null;
  verification_notes?: string | null;
  verified_at?: string | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type FracasAction = {
  id: number;
  fracas_case_id: number;
  status: "OPEN" | "IN_PROGRESS" | "DONE" | "VERIFIED" | "CANCELLED";
  description: string;
  owner_user_id?: string | null;
  due_date?: string | null;
  completed_at?: string | null;
  verified_at?: string | null;
};

export type EngineTrend = {
  id: number;
  amo_id: string;
  aircraft_serial_number: string;
  engine_position: string;
  engine_serial_number?: string | null;
  current_status?: EngineTrendStatus | null;
  previous_status?: EngineTrendStatus | null;
  last_upload_date?: string | null;
  last_trend_date?: string | null;
  last_review_date?: string | null;
  reviewed_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ReliabilityPriority = {
  kind: "ALERT" | "OVERDUE_ACTION" | "ENGINE_SHIFT" | "DATA_QUALITY";
  severity: ReliabilitySeverity;
  title: string;
  summary?: string | null;
  occurred_at?: string | null;
  due_date?: string | null;
  relative_path: string;
  entity_id?: string | null;
};

export type ReliabilityFreshness = {
  source: string;
  status: "CURRENT" | "STALE" | "MISSING" | "FAILED" | "PENDING";
  latest_record_at?: string | null;
  age_days?: number | null;
  issue_count: number;
  detail?: string | null;
};

export type ReliabilityWorkbench = {
  generated_at: string;
  counts: {
    open_alerts: number;
    critical_alerts: number;
    active_cases: number;
    overdue_actions: number;
    engine_shifts: number;
    recent_events: number;
    data_quality_issues: number;
  };
  priorities: ReliabilityPriority[];
  recent_events: ReliabilityEvent[];
  active_cases: FracasCase[];
  open_alerts: ReliabilityAlert[];
  engine_shifts: EngineTrend[];
  data_freshness: ReliabilityFreshness[];
};

function queryString(values: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function getReliabilityWorkbench(limit = 8): Promise<ReliabilityWorkbench> {
  return apiRequest(`/reliability/workbench${queryString({ limit })}`, {
    cacheTtlMs: 30_000,
    persistCache: true,
    staleWhileOfflineMs: 30 * 60_000,
  });
}

export function listReliabilityEvents(filters: {
  eventType?: ReliabilityEventType;
  severity?: ReliabilitySeverity;
  aircraftSerialNumber?: string;
  q?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ReliabilityEvent[]> {
  return apiRequest(`/reliability/events${queryString({
    event_type: filters.eventType,
    severity: filters.severity,
    aircraft_serial_number: filters.aircraftSerialNumber,
    q: filters.q,
    limit: filters.limit ?? 100,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 20_000, persistCache: true });
}

export function getReliabilityEvent(eventId: number): Promise<ReliabilityEvent> {
  return apiRequest(`/reliability/events/${eventId}`, { cacheTtlMs: 20_000 });
}

export function listReliabilityAlerts(filters: {
  status?: ReliabilityAlertStatus;
  severity?: ReliabilitySeverity;
  limit?: number;
  offset?: number;
} = {}): Promise<ReliabilityAlert[]> {
  return apiRequest(`/reliability/alerts${queryString({
    status: filters.status,
    severity: filters.severity,
    limit: filters.limit ?? 100,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 15_000, persistCache: true });
}

export function getReliabilityAlert(alertId: number): Promise<ReliabilityAlert> {
  return apiRequest(`/reliability/alerts/${alertId}`, { cacheTtlMs: 15_000 });
}

export function listFracasCases(filters: {
  status?: FracasStatus;
  severity?: ReliabilitySeverity;
  limit?: number;
  offset?: number;
} = {}): Promise<FracasCase[]> {
  return apiRequest(`/reliability/fracas/cases${queryString({
    status: filters.status,
    severity: filters.severity,
    limit: filters.limit ?? 100,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 15_000, persistCache: true });
}

export function getFracasCase(caseId: number): Promise<FracasCase> {
  return apiRequest(`/reliability/fracas/cases/${caseId}`, { cacheTtlMs: 15_000 });
}

export function listFracasActions(caseId: number): Promise<FracasAction[]> {
  return apiRequest(`/reliability/fracas/cases/${caseId}/actions`, { cacheTtlMs: 15_000 });
}

export function listEngineTrendStatuses(filters: {
  currentStatus?: EngineTrendStatus;
  limit?: number;
  offset?: number;
} = {}): Promise<EngineTrend[]> {
  return apiRequest(`/reliability/engine-trends/fleet-status${queryString({
    current_status: filters.currentStatus,
    limit: filters.limit ?? 100,
    offset: filters.offset ?? 0,
  })}`, { cacheTtlMs: 30_000, persistCache: true });
}
