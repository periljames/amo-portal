import { getToken } from "./auth";
import { normaliseBaseUrl } from "./config";

export type DataMode = "REAL" | "DEMO";

export type OpsSnapshot = {
  generated_at: string;
  data_mode: DataMode;
  source?: string;
  overview?: Record<string, any>;
  slo?: Record<string, any>;
  capacity?: Record<string, any>;
  fleet?: { total?: number; critical?: number; warning?: number; items?: Array<Record<string, any>> };
  incidents?: { open?: number; items?: Array<Record<string, any>> };
  alerts?: { items?: Array<Record<string, any>>; total?: number };
  jobs?: { items?: Array<Record<string, any>>; total?: number };
  product?: Record<string, any>;
  commercial?: Record<string, any>;
  security?: Record<string, any>;
  changes?: { maintenance?: Array<Record<string, any>>; events?: Array<Record<string, any>> };
};

function base(): string {
  const configured = String(import.meta.env.VITE_PLATFORM_OPS_BASE_URL || "").trim();
  return configured ? normaliseBaseUrl(configured) : "";
}

function url(path: string): string {
  return `${base()}/ops/v1${path}`;
}

function headers(extra?: Record<string, string>): Record<string, string> {
  const token = getToken();
  return {
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url(path), {
    credentials: "include",
    ...init,
    headers: { ...headers(init?.body ? { "Content-Type": "application/json" } : undefined), ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`Platform operations request failed (${response.status})${body ? `: ${body.slice(0, 240)}` : ""}`);
  }
  return response.json() as Promise<T>;
}

export const platformOperationsApi = {
  snapshot: (mode: DataMode = "REAL") => request<OpsSnapshot>(`/snapshot?data_mode=${mode}`),
  tenant360: (tenantId: string, mode: DataMode = "REAL") => request<Record<string, any>>(`/tenants/${encodeURIComponent(tenantId)}?data_mode=${mode}`),
  users: (params: URLSearchParams) => request<Record<string, any>>(`/users?${params.toString()}`),
  createIncident: (payload: Record<string, any>) => request<Record<string, any>>("/incidents", { method: "POST", body: JSON.stringify(payload) }),
  resolveIncident: (id: string, reason: string) => request<Record<string, any>>(`/incidents/${encodeURIComponent(id)}/resolve`, { method: "POST", body: JSON.stringify({ reason }) }),
  bulk: (payload: Record<string, any>) => request<Record<string, any>>("/operations/bulk", { method: "POST", body: JSON.stringify(payload) }),
  approve: (id: string, reason: string) => request<Record<string, any>>(`/operations/${encodeURIComponent(id)}/approve`, { method: "POST", body: JSON.stringify({ reason }) }),
  scheduleMaintenance: (payload: Record<string, any>) => request<Record<string, any>>("/changes/maintenance", { method: "POST", body: JSON.stringify(payload) }),
};

export function operationsStreamUrl(mode: DataMode): string {
  return url(`/events?data_mode=${mode}`);
}
