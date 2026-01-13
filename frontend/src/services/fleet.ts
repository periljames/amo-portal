// src/services/fleet.ts
// Fleet-facing API helpers (aircraft compliance documents and alerts).

import { getToken, handleAuthFailure } from "./auth";

const API_BASE =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export type AircraftDocumentStatus =
  | "CURRENT"
  | "DUE_SOON"
  | "OVERDUE"
  | "OVERRIDDEN";

export type AircraftDocumentType =
  | "CERTIFICATE_OF_AIRWORTHINESS"
  | "CERTIFICATE_OF_REGISTRATION"
  | "AIRWORTHINESS_REVIEW_CERTIFICATE"
  | "RADIO_TELEPHONY_LICENSE"
  | "NOISE_CERTIFICATE"
  | "INSURANCE"
  | "WEIGHT_AND_BALANCE_SCHEDULE"
  | "MEL_APPROVAL"
  | "OTHER";

export type RegulatoryAuthority = "FAA" | "EASA" | "KCAA" | "CAA_UK" | "OTHER";

export interface AircraftDocument {
  id: number;
  aircraft_serial_number: string;
  document_type: AircraftDocumentType;
  authority: RegulatoryAuthority;
  title: string | null;
  reference_number: string | null;
  compliance_basis: string | null;
  issued_on: string | null;
  expires_on: string | null;
  alert_window_days: number;
  status: AircraftDocumentStatus;
  is_blocking: boolean;
  days_to_expiry: number | null;
  missing_evidence: boolean;
  file_original_name: string | null;
  file_storage_path: string | null;
  file_content_type: string | null;
  last_uploaded_at: string | null;
  last_uploaded_by_user_id: string | null;
  override_reason: string | null;
  override_expires_on: string | null;
  override_by_user_id: string | null;
  override_recorded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AircraftComplianceSummary {
  aircraft_serial_number: string;
  documents_total: number;
  is_blocking: boolean;
  blocking_documents: AircraftDocument[];
  due_soon_documents: AircraftDocument[];
  overdue_documents: AircraftDocument[];
  overrides: AircraftDocument[];
  documents: AircraftDocument[];
}

export interface AircraftUsageSummary {
  aircraft_serial_number: string;
  total_hours: number | null;
  total_cycles: number | null;
  seven_day_daily_average_hours: number | null;
  next_due_program_item_id: number | null;
  next_due_task_code: string | null;
  next_due_date: string | null;
  next_due_hours: number | null;
  next_due_cycles: number | null;
}

export interface AircraftRead {
  serial_number: string;
  registration: string;
  template?: string | null;
  make?: string | null;
  model?: string | null;
  home_base?: string | null;
  owner?: string | null;
  status?: string | null;
  is_active?: boolean;
  total_hours?: number | null;
  total_cycles?: number | null;
  created_at?: string;
  updated_at?: string;
  verification_status?: string;
}

export type TransferProgress = {
  loadedBytes: number;
  totalBytes?: number;
  percent?: number;
  megaBytesPerSecond: number;
  megaBitsPerSecond: number;
};

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
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Fleet API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
}

async function sendJson<T>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body ?? {}),
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Fleet API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
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

export async function listDocumentAlerts(params?: { due_within_days?: number }): Promise<AircraftDocument[]> {
  return fetchJson<AircraftDocument[]>(
    `/aircraft/document-alerts${toQuery(params ?? {})}`
  );
}

export async function listAircraft(params?: {
  template?: string;
  status?: string;
  is_active?: boolean;
}): Promise<AircraftRead[]> {
  return fetchJson<AircraftRead[]>(`/aircraft${toQuery(params ?? {})}`);
}

export async function listAircraftDocuments(serialNumber: string): Promise<AircraftDocument[]> {
  return fetchJson<AircraftDocument[]>(`/aircraft/${serialNumber}/documents`);
}

export async function getAircraftUsageSummary(
  serialNumber: string
): Promise<AircraftUsageSummary> {
  return fetchJson<AircraftUsageSummary>(`/aircraft/${serialNumber}/usage/summary`);
}

export async function getAircraftCompliance(serialNumber: string): Promise<AircraftComplianceSummary> {
  return fetchJson<AircraftComplianceSummary>(`/aircraft/${serialNumber}/compliance`);
}

export async function createAircraftDocument(
  serialNumber: string,
  body: {
    document_type: AircraftDocumentType;
    authority: RegulatoryAuthority;
    title?: string | null;
    reference_number?: string | null;
    compliance_basis?: string | null;
    issued_on?: string | null;
    expires_on?: string | null;
    alert_window_days?: number;
  }
): Promise<AircraftDocument> {
  return sendJson<AircraftDocument>(`/aircraft/${serialNumber}/documents`, "POST", body);
}

export async function updateAircraftDocument(
  documentId: number,
  body: Partial<{
    title: string | null;
    reference_number: string | null;
    compliance_basis: string | null;
    issued_on: string | null;
    expires_on: string | null;
    alert_window_days: number;
    status: AircraftDocumentStatus;
  }>
): Promise<AircraftDocument> {
  return sendJson<AircraftDocument>(`/aircraft/documents/${documentId}`, "PUT", body);
}

export async function uploadAircraftDocumentFile(
  documentId: number,
  file: File
): Promise<AircraftDocument> {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/aircraft/documents/${documentId}/upload`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: form,
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Fleet API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as AircraftDocument;
}

export async function downloadAircraftDocumentFile(
  documentId: number,
  onProgress?: (progress: TransferProgress) => void
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    xhr.open("GET", `${API_BASE}/aircraft/documents/${documentId}/download`);
    const token = getToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
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
        const message = xhr.responseText || `Fleet API ${xhr.status}`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading document evidence."));
    });

    xhr.send();
  });
}

export async function downloadAircraftDocumentsZip(
  documentIds: number[],
  onProgress?: (progress: TransferProgress) => void
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAt = performance.now();
    xhr.open("POST", `${API_BASE}/aircraft/documents/download-zip`);
    const token = getToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.setRequestHeader("Content-Type", "application/json");
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
        const message = xhr.responseText || `Fleet API ${xhr.status}`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading document bundle."));
    });

    xhr.send(JSON.stringify({ document_ids: documentIds }));
  });
}

export async function overrideAircraftDocument(
  documentId: number,
  body: { reason: string; override_expires_on?: string | null }
): Promise<AircraftDocument> {
  return sendJson<AircraftDocument>(
    `/aircraft/documents/${documentId}/override`,
    "POST",
    body
  );
}

export async function clearAircraftDocumentOverride(documentId: number): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/aircraft/documents/${documentId}/override`, {
    method: "DELETE",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Fleet API ${res.status}: ${text || res.statusText}`);
  }
}
