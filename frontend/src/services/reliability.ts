// src/services/reliability.ts
import { getToken, handleAuthFailure, markSessionActivity } from "./auth";
import { getApiBaseUrl } from "./config";

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

function buildAuthHeader(): HeadersInit {
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
    url: `${API_BASE}/reliability/fracas/${caseId}/evidence-pack`,
    headers: buildAuthHeader(),
    fallbackFilename: `fracas-${caseId}-evidence-pack.zip`,
    retries: 3,
  });
}
