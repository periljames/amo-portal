import { apiRequest, qmsPath } from "./apiClient";
import { getToken } from "./auth";
import { getApiBaseUrl } from "./config";

export type GeneratedAuditReportArtifact = {
  id: string;
  audit_id: string;
  source_snapshot_hash: string;
  template_version: string;
  renderer_version: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  generated_by_user_id: string | null;
  created_at: string;
};

export type AuditReportComposition = {
  audit: {
    id: string;
    audit_ref: string;
    title: string;
    status: string;
    scope: string | null;
    criteria: string | null;
    actual_start: string | null;
    actual_end: string | null;
  };
  checklist_counts: Record<string, number>;
  findings_count: number;
  cars_count: number;
  preparation_documents_count: number;
  artifacts: GeneratedAuditReportArtifact[];
};

export function getAuditReportComposition(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditReportComposition>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-composition`), {
    timeoutMs: 20_000,
    cacheTtlMs: 0,
    signal,
  });
}

export function generateAuditClosingReport(amoCode: string, auditId: string) {
  return apiRequest<GeneratedAuditReportArtifact>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-composition/generate`), {
    method: "POST",
    timeoutMs: 60_000,
  });
}

export async function downloadGeneratedAuditReport(amoCode: string, auditId: string, artifactId: string): Promise<Blob> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}${qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-composition/artifacts/${encodeURIComponent(artifactId)}/download`)}`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    credentials: "include",
  });
  if (!response.ok) throw new Error(`Generated audit report download failed with status ${response.status}.`);
  return response.blob();
}
