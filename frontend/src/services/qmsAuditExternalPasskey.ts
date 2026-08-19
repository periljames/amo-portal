import {
  createCredential,
  decodeCreationOptions,
  decodeRequestOptions,
  getAssertion,
  isSecureContextAvailable,
  isWebAuthnSupported,
  serializeAssertionCredential,
  serializeRegistrationCredential,
} from "../lib/webauthn";
import { getApiBaseUrl } from "./config";
import type { AuditGuestReadModel } from "./qmsAuditExternalAccess";

export type ExternalPasskeyStatus = {
  required: true;
  registered: boolean;
  participant_type: "EXTERNAL_AUDITOR";
  display_name: string;
  organisation: string | null;
  expires_at: string;
};

type CeremonyOptions = { challenge_id: string; options: Record<string, unknown> };

export class ExternalPasskeyRequestError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ExternalPasskeyRequestError";
    this.status = status;
  }
}

async function request<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string"
        ? String((detail as { message: unknown }).message)
        : `External auditor passkey request failed with status ${response.status}.`;
    throw new ExternalPasskeyRequestError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export function getExternalAuditPasskeyStatus(token: string) {
  return request<ExternalPasskeyStatus>("/quality/audit-access/passkey/status", { token });
}

export async function activateExternalAuditPasskeySession(token: string): Promise<AuditGuestReadModel> {
  if (!isWebAuthnSupported() || !isSecureContextAvailable()) {
    throw new Error("This external-auditor invitation requires a passkey, but the current browser/origin cannot perform a secure WebAuthn ceremony.");
  }
  const status = await getExternalAuditPasskeyStatus(token);
  if (status.registered) {
    const options = await request<CeremonyOptions>("/quality/audit-access/passkey/assertion/options", { token });
    const assertion = await getAssertion(decodeRequestOptions(options.options));
    if (!assertion) throw new Error("Passkey verification was cancelled.");
    return request<AuditGuestReadModel>("/quality/audit-access/passkey/assertion/verify", {
      token,
      challenge_id: options.challenge_id,
      credential: serializeAssertionCredential(assertion),
    });
  }

  const options = await request<CeremonyOptions>("/quality/audit-access/passkey/registration/options", { token });
  const credential = await createCredential(decodeCreationOptions(options.options));
  if (!credential) throw new Error("Passkey registration was cancelled.");
  return request<AuditGuestReadModel>("/quality/audit-access/passkey/registration/verify", {
    token,
    challenge_id: options.challenge_id,
    credential: serializeRegistrationCredential(credential),
    nickname: "External audit passkey",
  });
}
