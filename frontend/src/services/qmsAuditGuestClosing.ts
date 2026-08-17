import { getApiBaseUrl } from "./config";

export type AuditGuestClosingContext = {
  available: boolean;
  report: {
    id: string;
    revision_no: number;
    status: "DRAFT" | "INTERNAL_REVIEW";
    filename: string;
    sha256: string;
    report_snapshot: Record<string, unknown>;
  } | null;
  acknowledgement: AuditGuestClosingAcknowledgement | null;
};

export type AuditGuestClosingAcknowledgement = {
  id: string;
  audit_id: string;
  participant_id: string;
  report_revision_id: string;
  report_sha256: string;
  acknowledgement_status: "ACKNOWLEDGED" | "COMMENTED" | "DECLINED_TO_ACKNOWLEDGE";
  comments: string | null;
  created_at: string | null;
};

async function publicRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
      throw new Error((detail as { message: string }).message);
    }
    throw new Error(`Audit closing request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export function getAuditGuestClosingContext() {
  return publicRequest<AuditGuestClosingContext>("/quality/audit-access/closing");
}

export function recordAuditGuestClosingAcknowledgement(payload: {
  reportRevisionId: string;
  reportSha256: string;
  acknowledgementStatus: AuditGuestClosingAcknowledgement["acknowledgement_status"];
  comments?: string | null;
}) {
  return publicRequest<AuditGuestClosingAcknowledgement>("/quality/audit-access/closing/acknowledgements", {
    method: "POST",
    body: JSON.stringify({
      report_revision_id: payload.reportRevisionId,
      report_sha256: payload.reportSha256,
      acknowledgement_status: payload.acknowledgementStatus,
      comments: payload.comments?.trim() || null,
    }),
  });
}
