import { apiRequest, qmsPath } from "./apiClient";

export type AuditOutputPolicyType = "NONE" | "REPORT_ONLY" | "APPROVAL_LETTER" | "CERTIFICATE" | "ATTESTATION";

export type AuditOutputPolicyRevision = {
  id: string;
  revision_no: number;
  artifact_policy: AuditOutputPolicyType;
  artifact_title: string | null;
  artifact_statement: string | null;
  rationale: string;
  created_by_user_id: string | null;
  created_at: string | null;
};

export type AuditOutputPolicy = {
  configured: boolean;
  current: AuditOutputPolicyRevision | null;
};

export type AuditSignatureEvidence = {
  id: string;
  audit_id: string;
  report_revision_id: string;
  signer_user_id: string;
  method: "PASSWORD_REAUTH";
  purpose: "ISSUED_REPORT";
  artifact_sha256: string;
  reason: string;
  signature_digest: string;
  signed_at: string | null;
};

export type AuditAssuranceArtifact = {
  id: string;
  audit_id: string;
  output_policy_revision_id: string;
  artifact_type: "APPROVAL_LETTER" | "CERTIFICATE" | "ATTESTATION";
  source_report_revision_id: string;
  signature_evidence_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_by_user_id: string | null;
  created_at: string | null;
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function getAuditOutputPolicy(amoCode: string, signal?: AbortSignal) {
  return apiRequest<AuditOutputPolicy>(qmsPath(amoCode, "/audit-output-policy"), {
    timeoutMs: 15_000,
    cacheTtlMs: 2_000,
    signal,
  });
}

export function listAuditSignatureEvidence(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditSignatureEvidence[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/signature-evidence`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function signIssuedAuditReport(
  amoCode: string,
  auditId: string,
  reauthValue: string,
  reason: string,
) {
  return apiRequest<AuditSignatureEvidence>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/signature-evidence/password-reauth`),
    json("POST", { password: reauthValue, reason }),
  );
}

export function listAuditAssuranceArtifacts(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditAssuranceArtifact[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/assurance-artifacts`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function generateAuditAssuranceArtifact(amoCode: string, auditId: string, signatureEvidenceId: string) {
  return apiRequest<AuditAssuranceArtifact>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/assurance-artifacts/generate`),
    json("POST", { signature_evidence_id: signatureEvidenceId }),
  );
}
