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
  method: "PASSWORD_REAUTH" | "WEBAUTHN";
  purpose: "ISSUED_REPORT" | "APPROVED_REPORT";
  artifact_sha256: string;
  reason: string;
  signature_digest: string;
  credential_id_hash?: string | null;
  webauthn_sign_count?: number | null;
  webauthn_origin?: string | null;
  webauthn_rp_id?: string | null;
  ceremony_sha256?: string | null;
  signed_at: string | null;
};

export type AuditWebAuthnCredential = {
  id: string;
  credential_id_masked: string;
  nickname: string | null;
  transports: string[];
  sign_count: number;
  is_active: boolean;
  created_at: string | null;
  last_used_at: string | null;
};

export type AuditWebAuthnOptions = {
  already_signed?: boolean;
  challenge_id?: string;
  report_sha256?: string;
  options?: Record<string, unknown>;
  signature?: AuditSignatureEvidence;
};

export type AuditClosingAcknowledgement = {
  id: string;
  audit_id: string;
  participant_id: string;
  report_revision_id: string;
  report_sha256: string;
  acknowledgement_status: "ACKNOWLEDGED" | "COMMENTED" | "DECLINED_TO_ACKNOWLEDGE";
  comments: string | null;
  created_at: string | null;
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

export type AuditVerificationToken = {
  id: string;
  expires_at: string;
  verification_url: string;
  token: string;
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

export function listAuditClosingAcknowledgements(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditClosingAcknowledgement[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/closing-acknowledgements`),
    { timeoutMs: 15_000, cacheTtlMs: 1_500, signal },
  );
}

export function listAuditWebAuthnCredentials(amoCode: string, signal?: AbortSignal) {
  return apiRequest<{ items: AuditWebAuthnCredential[] }>(qmsPath(amoCode, "/audit-webauthn/credentials"), {
    timeoutMs: 15_000,
    cacheTtlMs: 1_500,
    signal,
  });
}

export function getAuditWebAuthnRegistrationOptions(amoCode: string) {
  return apiRequest<{ challenge_id: string; options: Record<string, unknown> }>(
    qmsPath(amoCode, "/audit-webauthn/registration/options"),
    { method: "POST", timeoutMs: 15_000 },
  );
}

export function verifyAuditWebAuthnRegistration(
  amoCode: string,
  challengeId: string,
  credential: Record<string, unknown>,
  nickname?: string | null,
) {
  return apiRequest<AuditWebAuthnCredential>(
    qmsPath(amoCode, "/audit-webauthn/registration/verify"),
    json("POST", { challenge_id: challengeId, credential, nickname: nickname || null }),
  );
}

export function revokeAuditWebAuthnCredential(amoCode: string, credentialId: string) {
  return apiRequest<void>(
    qmsPath(amoCode, `/audit-webauthn/credentials/${encodeURIComponent(credentialId)}`),
    { method: "DELETE", timeoutMs: 15_000 },
  );
}

export function getApprovedAuditReportSignatureOptions(amoCode: string, auditId: string, revisionId: string) {
  return apiRequest<AuditWebAuthnOptions>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-revisions/${encodeURIComponent(revisionId)}/signature/options`),
    { method: "POST", timeoutMs: 15_000 },
  );
}

export function verifyApprovedAuditReportSignature(
  amoCode: string,
  auditId: string,
  revisionId: string,
  challengeId: string,
  credential: Record<string, unknown>,
  reason: string,
) {
  return apiRequest<AuditSignatureEvidence>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/report-revisions/${encodeURIComponent(revisionId)}/signature/verify`),
    json("POST", { challenge_id: challengeId, credential, reason }),
  );
}

// Compatibility fallback retained for previously issued evidence. The governed
// live-audit issue gate does not accept this as a substitute for WebAuthn.
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

export function createAuditVerificationToken(
  amoCode: string,
  auditId: string,
  options: { assuranceArtifactId?: string | null; expiresInDays?: number } = {},
) {
  return apiRequest<AuditVerificationToken>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/verification-tokens`),
    json("POST", {
      assurance_artifact_id: options.assuranceArtifactId || null,
      expires_in_days: options.expiresInDays ?? 180,
    }),
  );
}
