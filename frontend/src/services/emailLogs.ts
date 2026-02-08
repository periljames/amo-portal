import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";

export type EmailLogStatus =
  | "QUEUED"
  | "SENT"
  | "FAILED"
  | "SKIPPED_NO_PROVIDER";

export interface EmailLog {
  id: string;
  amo_id: string;
  created_at: string;
  sent_at: string | null;
  recipient: string;
  subject: string;
  template_key: string;
  status: EmailLogStatus;
  error?: string | null;
  context_json?: Record<string, unknown> | null;
  correlation_id?: string | null;
}

type QueryVal = string | number | boolean | null | undefined;

const API_BASE = getApiBaseUrl();

function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    qs.set(key, String(value));
  });
  const str = qs.toString();
  return str ? `?${str}` : "";
}

export async function listEmailLogs(params: {
  status?: EmailLogStatus;
  templateKey?: string;
  recipient?: string;
  start?: string;
  end?: string;
}): Promise<EmailLog[]> {
  const token = getToken();
  const query = toQuery({
    status: params.status,
    template_key: params.templateKey,
    recipient: params.recipient,
    start: params.start,
    end: params.end,
  });
  const resp = await fetch(`${API_BASE}/email-logs${query}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!resp.ok) {
    if (resp.status === 401 || resp.status === 403) {
      handleAuthFailure();
    }
    throw new Error("Failed to load email logs.");
  }
  return (await resp.json()) as EmailLog[];
}
