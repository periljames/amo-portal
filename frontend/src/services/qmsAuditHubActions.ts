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

async function hubFetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  beginBackgroundLoading();
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort("timeout"), 20000);
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      method: "GET",
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      signal: controller.signal,
    });
    window.clearTimeout(timeout);

    if (res.status === 401) {
      handleAuthFailure("expired");
      throw new Error("Session expired. Please sign in again.");
    }

    if (res.status === 503) {
      const text = await res.text().catch(() => "");
      throw new Error(text || "Service unavailable. Please retry or contact support.");
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
    }

    return (await res.json()) as T;
  } finally {
    endBackgroundLoading();
  }
}

async function hubSendJson<T>(path: string, method: "POST" | "PATCH" | "DELETE", body: unknown): Promise<T> {
  const token = getToken();
  beginLoading();
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort("timeout"), 45000);
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body ?? {}),
      credentials: "include",
      signal: controller.signal,
    });
    window.clearTimeout(timeout);

    if (res.status === 401) {
      handleAuthFailure("expired");
      throw new Error("Session expired. Please sign in again.");
    }

    if (res.status === 503) {
      const text = await res.text().catch(() => "");
      throw new Error(text || "Service unavailable. Please retry or contact support.");
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
    }

    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } finally {
    endLoading();
  }
}

export async function qmsListCarActions(carId: string): Promise<CARActionOut[]> {
  return hubFetchJson<CARActionOut[]>(`/quality/cars/${encodeURIComponent(carId)}/actions`);
}

export async function qmsAddCarAction(carId: string, payload: CARActionCreate): Promise<CARActionOut> {
  return hubSendJson<CARActionOut>(`/quality/cars/${encodeURIComponent(carId)}/actions`, "POST", {
    action_type: payload.action_type ?? "COMMENT",
    message: payload.message,
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
  payload: QMSAuditReportSharePayload
): Promise<QMSAuditReportShareOut> {
  return hubSendJson<QMSAuditReportShareOut>(`/quality/audits/${encodeURIComponent(auditId)}/report/share`, "POST", {
    recipient_groups: payload.recipient_groups,
    message: payload.message ?? null,
  });
}
