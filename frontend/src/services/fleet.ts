// src/services/fleet.ts
// Fleet-facing API helpers (aircraft compliance documents and alerts).

import { getToken, handleAuthFailure } from "./auth";
import { downloadWithXhr, type DownloadedFile } from "../utils/downloads";
import { getApiBaseUrl } from "./config";
import { portalFetch } from "./offlineHttp";

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

const API_BASE = getApiBaseUrl();
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;
const DOCUMENT_ALERTS_TIMEOUT_MS = 4_000;

type FetchJsonOptions<T> = {
  timeoutMs?: number;
  fallbackOnNotFound?: T;
  cacheTtlMs?: number;
};

function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    qs.set(key, String(value));
  });
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : "";
}

function authenticatedHeaders(json = false): Headers {
  const token = getToken();
  const headers = new Headers({ Accept: "application/json" });
  if (json) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function parseFleetError(response: Response): Promise<Error> {
  const text = await response.text().catch(() => "");
  return new Error(`Fleet API ${response.status}: ${text || response.statusText}`);
}

async function fetchJson<T>(path: string, options?: FetchJsonOptions<T>): Promise<T> {
  const response = await portalFetch(path, {
    method: "GET",
    headers: authenticatedHeaders(),
    credentials: "include",
    timeoutMs: options?.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS,
    offline: {
      cache: true,
      cacheTtlMs: options?.cacheTtlMs ?? 5 * 60_000,
      allowStaleFallback: true,
    },
  });

  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (response.status === 404 && options && "fallbackOnNotFound" in options) {
    return options.fallbackOnNotFound as T;
  }
  if (!response.ok) throw await parseFleetError(response);
  return (await response.json()) as T;
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PUT",
  body: unknown,
  options: { queueMutation?: boolean; entityType?: string; entityId?: string } = {},
): Promise<T> {
  const response = await portalFetch(path, {
    method,
    headers: authenticatedHeaders(true),
    body: JSON.stringify(body ?? {}),
    credentials: "include",
    offline: {
      queueMutation: options.queueMutation === true,
      entityType: options.entityType,
      entityId: options.entityId,
    },
  });

  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw await parseFleetError(response);
  return (await response.json()) as T;
}

function buildSpeed(
  loadedBytes: number,
  totalBytes: number | undefined,
  startedAt: number,
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
    `/aircraft/document-alerts${toQuery(params ?? {})}`,
    {
      timeoutMs: DOCUMENT_ALERTS_TIMEOUT_MS,
      fallbackOnNotFound: [],
      cacheTtlMs: 2 * 60_000,
    },
  );
}

export async function listAircraft(params?: {
  template?: string;
  status?: string;
  is_active?: boolean;
}): Promise<AircraftRead[]> {
  return fetchJson<AircraftRead[]>(`/aircraft/${toQuery(params ?? {})}`, { cacheTtlMs: 10 * 60_000 });
}

export async function listAircraftDocuments(serialNumber: string): Promise<AircraftDocument[]> {
  return fetchJson<AircraftDocument[]>(`/aircraft/${encodeURIComponent(serialNumber)}/documents`);
}

export async function getAircraftUsageSummary(serialNumber: string): Promise<AircraftUsageSummary> {
  return fetchJson<AircraftUsageSummary>(`/aircraft/${encodeURIComponent(serialNumber)}/usage/summary`, { cacheTtlMs: 2 * 60_000 });
}

export async function getAircraftCompliance(serialNumber: string): Promise<AircraftComplianceSummary> {
  return fetchJson<AircraftComplianceSummary>(`/aircraft/${encodeURIComponent(serialNumber)}/compliance`, { cacheTtlMs: 2 * 60_000 });
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
  },
): Promise<AircraftDocument> {
  // Compliance-record creation stays live-only to prevent duplicate evidence records.
  return sendJson<AircraftDocument>(`/aircraft/${encodeURIComponent(serialNumber)}/documents`, "POST", body);
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
  }>,
): Promise<AircraftDocument> {
  return sendJson<AircraftDocument>(`/aircraft/documents/${documentId}`, "PUT", body, {
    queueMutation: true,
    entityType: "aircraft-document",
    entityId: String(documentId),
  });
}

export async function uploadAircraftDocumentFile(
  documentId: number,
  file: File,
): Promise<AircraftDocument> {
  const form = new FormData();
  form.append("file", file);
  const response = await portalFetch(`/aircraft/documents/${documentId}/upload`, {
    method: "POST",
    headers: authenticatedHeaders(),
    body: form,
    credentials: "include",
    timeoutMs: 60_000,
    offline: { cache: false, queueMutation: false },
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw await parseFleetError(response);
  return (await response.json()) as AircraftDocument;
}

export async function downloadAircraftDocumentFile(
  documentId: number,
  onProgress?: (progress: TransferProgress) => void,
): Promise<DownloadedFile> {
  const startedAt = performance.now();
  const token = getToken();
  return downloadWithXhr({
    url: `${API_BASE}/aircraft/documents/${documentId}/download`,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    fallbackFilename: `aircraft-document-${documentId}`,
    onProgress: onProgress ? (loaded, total) => onProgress(buildSpeed(loaded, total, startedAt)) : undefined,
    retries: 2,
  });
}

export async function downloadAircraftDocumentsZip(
  documentIds: number[],
  onProgress?: (progress: TransferProgress) => void,
): Promise<DownloadedFile> {
  const startedAt = performance.now();
  const token = getToken();
  return downloadWithXhr({
    url: `${API_BASE}/aircraft/documents/download-zip`,
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ document_ids: documentIds }),
    fallbackFilename: "aircraft-documents.zip",
    onProgress: onProgress ? (loaded, total) => onProgress(buildSpeed(loaded, total, startedAt)) : undefined,
    retries: 2,
  });
}

export async function overrideAircraftDocument(
  documentId: number,
  body: { reason: string; override_expires_on?: string | null },
): Promise<AircraftDocument> {
  // Regulatory overrides require immediate server confirmation.
  return sendJson<AircraftDocument>(`/aircraft/documents/${documentId}/override`, "POST", body);
}

export async function clearAircraftDocumentOverride(documentId: number): Promise<void> {
  const response = await portalFetch(`/aircraft/documents/${documentId}/override`, {
    method: "DELETE",
    headers: authenticatedHeaders(),
    credentials: "include",
    offline: { cache: false, queueMutation: false },
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw await parseFleetError(response);
}
