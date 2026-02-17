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

export async function fetchHealthz(): Promise<{ status: string }> {
  const res = await fetch(`${getApiBaseUrl()}/healthz`, { credentials: "include" });
  if (!res.ok) throw new Error(`healthz failed ${res.status}`);
  return res.json();
}

export async function fetchServerTime(): Promise<{ epoch_ms: number }> {
  const res = await fetch(`${getApiBaseUrl()}/time`, { credentials: "include" });
  if (!res.ok) throw new Error(`time failed ${res.status}`);
  return res.json();
}
