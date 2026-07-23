import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import { beginBackgroundLoading, beginLoading, endBackgroundLoading, endLoading } from "./loading";

export type CARActionType = "COMMENT" | "STATUS_CHANGE" | "REMINDER" | "ESCALATION" | "ASSIGNMENT" | string;

export interface CARActionOut {
  id: string;
  car_id: string;
  action_type: CARActionType;
  message: string;
  actor_user_id: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  delivery_status?: string | null;
  created_at: string;
}

export interface CARActionCreate {
  action_type?: CARActionType;
  message: string;
}

export interface QMSAuditReportSharePayload {
  recipient_groups: string[];
  message?: string | null;
}

export interface QMSAuditReportShareOut {
  audit_id: string;
  recipient_groups: string[];
  recipient_user_ids: string[];
  shared: number;
}

type HubRequestMode = "background" | "foreground";
type HubRequestMethod = "GET" | "POST" | "PATCH" | "DELETE";

const READ_TIMEOUT_MS = 20_000;
const WRITE_TIMEOUT_MS = 45_000;

async function readApiError(res: Response): Promise<string> {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await res.json().catch(() => null) as Record<string, unknown> | null;
    if (payload) {
      const detail = payload.detail;
      if (typeof detail === "string" && detail.trim()) return detail.trim();
      if (Array.isArray(detail) && detail.length > 0) return JSON.stringify(detail);
      for (const key of ["message", "error", "error_code"] as const) {
        const value = payload[key];
        if (typeof value === "string" && value.trim()) return value.trim();
      }
    }
  }

  const text = await res.text().catch(() => "");
  return text.trim();
}

async function hubRequest<T>(
  path: string,
  options: {
    method?: HubRequestMethod;
    body?: unknown;
    mode?: HubRequestMode;
    timeoutMs?: number;
  } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const mode = options.mode ?? (method === "GET" ? "background" : "foreground");
  const timeoutMs = options.timeoutMs ?? (method === "GET" ? READ_TIMEOUT_MS : WRITE_TIMEOUT_MS);
  const token = getToken();
  const controller = new AbortController();
  let timedOut = false;

  if (mode === "background") beginBackgroundLoading();
  else beginLoading();

  const timeout = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const hasBody = method !== "GET" && options.body !== undefined;
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(hasBody ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
      credentials: "include",
      signal: controller.signal,
    });

    if (res.status === 401) {
      handleAuthFailure("expired");
      throw new Error("Session expired. Please sign in again.");
    }

    if (!res.ok) {
      const detail = await readApiError(res);
      if (res.status === 503) {
        throw new Error(detail || "Quality service is temporarily unavailable. Please retry or contact support.");
      }
      throw new Error(detail || `Quality API request failed with status ${res.status}.`);
    }

    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (error) {
    if (timedOut) {
      throw new Error(`Quality API request timed out after ${Math.ceil(timeoutMs / 1000)} seconds.`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
    if (mode === "background") endBackgroundLoading();
    else endLoading();
  }
}

export async function qmsListCarActions(carId: string): Promise<CARActionOut[]> {
  return hubRequest<CARActionOut[]>(`/quality/cars/${encodeURIComponent(carId)}/actions`);
}

export async function qmsAddCarAction(carId: string, payload: CARActionCreate): Promise<CARActionOut> {
  return hubRequest<CARActionOut>(`/quality/cars/${encodeURIComponent(carId)}/actions`, {
    method: "POST",
    body: {
      action_type: payload.action_type ?? "COMMENT",
      message: payload.message,
    },
  });
}

export async function qmsRequestCarAccess(carId: string, message?: string): Promise<CARActionOut> {
  const cleanMessage = (message || "I can support resolution of this CAR. Please review and assign write access if appropriate.").trim();
  return qmsAddCarAction(carId, {
    action_type: "ASSIGNMENT",
    message: cleanMessage || "CAR access requested.",
  });
}

export async function qmsShareAuditReport(
  auditId: string,
  payload: QMSAuditReportSharePayload,
): Promise<QMSAuditReportShareOut> {
  return hubRequest<QMSAuditReportShareOut>(`/quality/audits/${encodeURIComponent(auditId)}/report/share`, {
    method: "POST",
    body: {
      recipient_groups: payload.recipient_groups,
      message: payload.message ?? null,
    },
  });
}
