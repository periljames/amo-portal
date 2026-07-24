import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import type {
  QualityAuditDocument,
  QualityAuditEvidenceReview,
  QualityAuditReportMetadata,
} from "./qmsAuditLifecycle";

async function readError(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json().catch(() => null) as Record<string, unknown> | null;
    if (payload) {
      const detail = payload.detail;
      if (typeof detail === "string") return detail;
      if (detail) return JSON.stringify(detail);
    }
  }
  return (await response.text().catch(() => "")).trim();
}

async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body instanceof FormData ? {} : init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
    credentials: "include",
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw new Error(await readError(response) || `Quality API request failed (${response.status}).`);
  return response;
}

export async function qmsListAuditEvidenceReviews(auditId: string): Promise<QualityAuditEvidenceReview[]> {
  const response = await authenticatedFetch(`/quality/audits/${encodeURIComponent(auditId)}/evidence/reviews`);
  return await response.json() as QualityAuditEvidenceReview[];
}

export async function qmsRecordReportDistribution(
  auditId: string,
  payload: {
    version_id: string;
    status: "NOT_DISTRIBUTED" | "PARTIAL" | "DISTRIBUTED";
    recipient_groups: string[];
    shared_count: number;
  },
): Promise<QualityAuditReportMetadata> {
  const response = await authenticatedFetch(`/quality/audits/${encodeURIComponent(auditId)}/documents/report/distribution`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return await response.json() as QualityAuditReportMetadata;
}

export async function qmsOpenLifecycleDocument(record: QualityAuditDocument): Promise<void> {
  const response = await authenticatedFetch(record.download_url, { method: "GET", cache: "no-store" });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function qmsDownloadLifecycleDocumentFile(record: QualityAuditDocument): Promise<void> {
  const response = await authenticatedFetch(record.download_url, { method: "GET", cache: "no-store" });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = record.filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
