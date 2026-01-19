// src/services/reliability.ts
import { getToken, handleAuthFailure } from "./auth";

const API_BASE =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";

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
  return (await res.json()) as ReliabilityReportRead;
}

export async function listReliabilityReports(): Promise<ReliabilityReportRead[]> {
  const token = getToken();
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
  return (await res.json()) as ReliabilityReportRead[];
}

export async function downloadReliabilityReport(
  reportId: number,
  onProgress?: (progress: TransferProgress) => void
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    xhr.open("GET", `${API_BASE}/reliability/reports/${reportId}/download`);
    const headers = buildAuthHeader();
    Object.entries(headers).forEach(([key, value]) => {
      xhr.setRequestHeader(key, value);
    });
    xhr.responseType = "blob";

    xhr.addEventListener("progress", (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : undefined;
      onProgress(buildSpeed(event.loaded, total, startedAt));
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const message = xhr.responseText || `Request failed (${xhr.status})`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading report."));
    });

    xhr.send();
  });
}
