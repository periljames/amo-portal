import { authHeaders } from "./auth";
import { apiDelete, apiGet, apiPost } from "./crs";
import {
  decodeCreationOptions,
  decodeRequestOptions,
  serializeAssertionCredential,
  serializeRegistrationCredential,
} from "../lib/webauthn";
import type {
  ArtifactAccess,
  ArtifactValidation,
  ArtifactVerifyLink,
  EvidenceBundle,
  PolicyOverride,
  ProviderReadiness,
  HashCompareResult,
  RequestCreatePayload,
  RequestCreateResult,
  SigningContext,
  TrustSummary,
  VerifyResult,
  WebAuthnCredential,
} from "../types/esign";

export const isEsignEntitled = async (): Promise<boolean> => {
  const rows = await apiGet<Array<{ key: string; is_unlimited: boolean; limit: number | null }>>("/billing/entitlements", { headers: authHeaders() });
  const match = rows.find((row) => row.key.toLowerCase() === "esign_module" || row.key.toLowerCase() === "esign");
  return Boolean(match && (match.is_unlimited || (match.limit ?? 0) > 0));
};

export const createRequest = (payload: RequestCreatePayload) => apiPost<RequestCreateResult>("/api/v1/esign/requests", payload, { headers: authHeaders() });
export const sendRequest = (requestId: string) => apiPost<{ id: string; status: string; sent_at?: string | null }>(`/api/v1/esign/requests/${encodeURIComponent(requestId)}/send`, {}, { headers: authHeaders() });
export const fetchSigningContext = (requestId: string) => apiGet<SigningContext>(`/api/v1/esign/requests/${encodeURIComponent(requestId)}/signing-context`, { headers: authHeaders() });
export const fetchArtifactValidation = (artifactId: string) => apiGet<ArtifactValidation>(`/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/validation`, { headers: authHeaders() });
export const revalidateArtifact = (artifactId: string) => apiPost<ArtifactValidation>(`/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/revalidate-now`, {}, { headers: authHeaders() });
export const fetchArtifactVerifyLink = (artifactId: string) => apiGet<ArtifactVerifyLink>(`/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/verify-link`, { headers: authHeaders() });
export const fetchPrivateArtifactAccess = (artifactId: string) => apiGet<ArtifactAccess>(`/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/access`, { headers: authHeaders() });
export const comparePrivateHash = (artifactId: string, payload: { provided_sha256?: string; file_base64?: string; compare_against?: string }) => apiPost<HashCompareResult>(`/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/compare-hash`, payload, { headers: authHeaders() });
export const privateArtifactPreviewUrl = (artifactId: string) => `/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/preview`;
export const privateArtifactDownloadUrl = (artifactId: string) => `/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/download`;
export const regenerateArtifactVerifyLink = (artifactId: string) => apiPost<ArtifactVerifyLink>(`/api/v1/esign/artifacts/${encodeURIComponent(artifactId)}/verify-link/regenerate`, {}, { headers: authHeaders() });
export const fetchProviderReadiness = () => apiGet<ProviderReadiness>("/api/v1/esign/provider/readiness", { headers: authHeaders() });
export const fetchTrustSummary = (query: URLSearchParams) => apiGet<TrustSummary>(`/api/v1/esign/reports/trust-summary?${query.toString()}`, { headers: authHeaders() });
export const createEvidenceBundle = (requestId: string) => apiPost<EvidenceBundle>(`/api/v1/esign/requests/${encodeURIComponent(requestId)}/evidence-bundle`, {}, { headers: authHeaders() });
export const getEvidenceBundle = (bundleId: string) => apiGet<EvidenceBundle>(`/api/v1/esign/evidence-bundles/${encodeURIComponent(bundleId)}`, { headers: authHeaders() });
export const getEvidenceDownloadUrl = (bundleId: string) => `/api/v1/esign/evidence-bundles/${encodeURIComponent(bundleId)}/download`;
export const listOverrides = (requestId: string) => apiGet<PolicyOverride[]>(`/api/v1/esign/requests/${encodeURIComponent(requestId)}/overrides`, { headers: authHeaders() });
export const createOverride = (requestId: string, payload: { override_type: string; justification: string; approved_by_user_id?: string; expires_at?: string }) => apiPost<PolicyOverride>(`/api/v1/esign/requests/${encodeURIComponent(requestId)}/overrides`, payload, { headers: authHeaders() });
export const verifyToken = (token: string) => apiGet<VerifyResult>(`/api/v1/esign/verify/${encodeURIComponent(token)}.json`);
export const fetchPublicArtifactAccess = (token: string) => apiGet<ArtifactAccess>(`/api/v1/esign/verify/${encodeURIComponent(token)}/artifact-access`);
export const comparePublicHash = (token: string, payload: { provided_sha256?: string; file_base64?: string; compare_against?: string }) => apiPost<HashCompareResult>(`/api/v1/esign/verify/${encodeURIComponent(token)}/compare-hash`, payload);
export const publicArtifactDownloadUrl = (token: string) => `/api/v1/esign/verify/${encodeURIComponent(token)}/download`;

export const listWebAuthnCredentials = () => apiGet<WebAuthnCredential[]>("/api/v1/esign/webauthn/credentials", { headers: authHeaders() });
export const removeWebAuthnCredential = (credentialId: string) => apiDelete<{ status: string }>(`/api/v1/esign/webauthn/credentials/${encodeURIComponent(credentialId)}`, { headers: authHeaders() });

export async function beginRegistration(displayName?: string | null): Promise<PublicKeyCredentialCreationOptions> {
  const out = await apiPost<{ options: Record<string, unknown> }>("/api/v1/esign/webauthn/registration/options", { display_name: displayName || null }, { headers: authHeaders() });
  return decodeCreationOptions(out.options);
}

export async function completeRegistration(credential: PublicKeyCredential): Promise<{ credential_id: string; sign_count: number }> {
  return apiPost<{ credential_id: string; sign_count: number }>(
    "/api/v1/esign/webauthn/registration/verify",
    { credential: serializeRegistrationCredential(credential) },
    { headers: authHeaders() }
  );
}

export async function startIntentAssertion(intentId: string): Promise<PublicKeyCredentialRequestOptions> {
  const out = await apiPost<{ options: Record<string, unknown> }>(`/api/v1/esign/intents/${encodeURIComponent(intentId)}/assertion/options`, {}, { headers: authHeaders() });
  return decodeRequestOptions(out.options);
}

export async function verifyIntentAssertion(intentId: string, assertion: PublicKeyCredential): Promise<{ artifact_id: string; verification_token: string }> {
  return apiPost<{ artifact_id: string; verification_token: string }>(
    `/api/v1/esign/intents/${encodeURIComponent(intentId)}/assertion/verify-and-sign`,
    {
      credential: serializeAssertionCredential(assertion),
    },
    { headers: authHeaders() }
  );
}
