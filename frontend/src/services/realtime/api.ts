import { getApiBaseUrl } from "../config";
import { getToken } from "../auth";
import type { RealtimeTokenResponse } from "./types";

export class RealtimeHttpError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "RealtimeHttpError";
    this.status = status;
  }
}

export async function fetchRealtimeToken(): Promise<RealtimeTokenResponse> {
  const token = getToken();
  if (!token) {
    throw new RealtimeHttpError("token request skipped (no session token)", 401);
  }

  const res = await fetch(`${getApiBaseUrl()}/api/realtime/token`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    credentials: "include",
  });
  if (!res.ok) throw new RealtimeHttpError(`token request failed (${res.status})`, res.status);
  return res.json();
}

/**
 * Realtime only needs process liveness here. Full readiness (/healthz or
 * /readyz) also includes database, migration and worker-family checks and may
 * legitimately return 503 while the API process remains reachable. Treating
 * that as realtime transport failure creates false degraded/offline state and
 * can unnecessarily gate unrelated interactive work such as QMS rescheduling.
 *
 * Keep the historical function name for call-site compatibility, but probe the
 * dedicated process-only /livez endpoint and normalise its response to the
 * status shape expected by RealtimeProvider.
 */
export async function fetchHealthz(): Promise<{ status: string }> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), 5000);
  try {
    const res = await fetch(`${getApiBaseUrl()}/livez`, {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json", "X-AMO-Silent-Error": "1" },
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`livez failed ${res.status}`);
    const body = await res.json().catch(() => null) as { status?: unknown; process?: unknown } | null;
    if (body?.status !== "alive" && body?.process !== true) {
      throw new Error("livez returned an invalid liveness response");
    }
    return { status: "ok" };
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function fetchServerTime(): Promise<{ epoch_ms: number }> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), 5000);
  const res = await fetch(`${getApiBaseUrl()}/time`, { credentials: "include", signal: controller.signal });
  window.clearTimeout(timeout);
  if (!res.ok) throw new Error(`time failed ${res.status}`);
  return res.json();
}
