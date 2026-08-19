import { getApiBaseUrl } from "./config";

export type PublicAuditVerification = {
  valid: true;
  audit: { audit_ref: string; title: string };
  report: {
    revision_no: number;
    status: "ISSUED";
    filename: string;
    sha256: string;
    issued_at: string | null;
  };
  signature: {
    method: "WEBAUTHN";
    purpose: "APPROVED_REPORT" | "ISSUED_REPORT";
    signed_at: string | null;
    credential_id_hash: string | null;
    ceremony_sha256: string | null;
  };
  assurance_artifact: {
    artifact_type: "APPROVAL_LETTER" | "CERTIFICATE" | "ATTESTATION";
    filename: string;
    sha256: string;
  } | null;
  verification: { expires_at: string };
};

async function publicJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
    credentials: "omit",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || "This verification record is invalid, expired, revoked, or unavailable.");
  }
  return response.json() as Promise<T>;
}

export function getPublicAuditVerification(token: string) {
  return publicJson<PublicAuditVerification>(`/quality/audit-verification/${encodeURIComponent(token)}`);
}

export function comparePublicAuditVerificationHash(token: string, sha256: string) {
  return publicJson<{ matches: boolean; governed_sha256: string; artifact_type: string }>(
    `/quality/audit-verification/${encodeURIComponent(token)}/compare-hash`,
    { method: "POST", body: JSON.stringify({ sha256: sha256.trim().toLowerCase() }) },
  );
}
