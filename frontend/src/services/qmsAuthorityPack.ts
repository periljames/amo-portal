import { apiRequest, qmsPath } from "./apiClient";
import { getToken } from "./auth";
import { getApiBaseUrl } from "./config";
import { downloadWithFetch, saveDownloadedFile, type DownloadedFile } from "../utils/downloads";

export type AuthoritySubmissionAttestation = {
  id: string;
  audit_id: string;
  report_revision_id: string;
  report_sha256: string;
  rationale: string;
  attested_by_user_id: string;
  attested_at: string;
  pack_filename: string | null;
  pack_content_type: string | null;
  pack_size_bytes: number | null;
  pack_sha256: string | null;
};

export type AuthorityAttestationResponse = {
  attestation: AuthoritySubmissionAttestation | null;
};

export type AuthorityAttestationInput = {
  report_revision_id: string;
  report_sha256: string;
  rationale: string;
};

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function attestAuthoritySubmission(
  amoCode: string,
  auditId: string,
  payload: AuthorityAttestationInput,
) {
  return apiRequest<AuthorityAttestationResponse>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/authority-attestation`),
    json(payload),
  );
}

export function getAuthorityAttestation(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuthorityAttestationResponse>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/authority-attestation`),
    { timeoutMs: 15_000, cacheTtlMs: 0, signal },
  );
}

export function generateAuthorityPack(amoCode: string, auditId: string) {
  return apiRequest<AuthorityAttestationResponse>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/authority-pack`),
    { method: "POST", timeoutMs: 60_000 },
  );
}

export async function downloadAuthorityPack(amoCode: string, auditId: string): Promise<DownloadedFile> {
  const token = getToken();
  const downloaded = await downloadWithFetch(
    `${getApiBaseUrl()}${qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/authority-pack/download`)}`,
    {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      credentials: "include",
    },
    `${auditId}-authority-pack.zip`,
  );
  saveDownloadedFile(downloaded);
  return downloaded;
}
