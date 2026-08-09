import { getToken } from "./auth";
import { normaliseBaseUrl } from "./config";

export type DataMode = "REAL" | "DEMO";
export type OpsRange = "15m" | "1h" | "6h" | "24h" | "7d" | "30d";

export type OpsSnapshot = {
  generated_at: string;
  data_mode: DataMode;
  source?: string;
  freshness?: { stale?: boolean; age_seconds?: number | null; last_error?: string | null; source?: string };
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
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type TenantHealthQuery = {
  data_mode?: DataMode;
  health?: string;
  active?: boolean;
  q?: string;
  min_users?: number;
  max_users?: number;
  sort?: "health" | "name" | "traffic" | "users";
  limit?: number;
  cursor?: string | null;
};

function queryString(values: Record<string, unknown>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  });
  return params.toString();
}

export const platformOperationsApi = {
  bootstrap: (mode: DataMode = "REAL") => request<{ snapshot: OpsSnapshot; query_registry: Record<string, any>; supported_ranges: OpsRange[]; arbitrary_promql: boolean }>(`/bootstrap?data_mode=${mode}`),
  snapshot: (mode: DataMode = "REAL") => request<OpsSnapshot>(`/snapshot?data_mode=${mode}`),
  nodes: () => request<Record<string, any>>("/nodes"),
  node: (nodeId: string) => request<Record<string, any>>(`/nodes/${encodeURIComponent(nodeId)}`),
  nodeTimeseries: (nodeId: string, metric: string, range: OpsRange = "1h") => request<Record<string, any>>(`/nodes/${encodeURIComponent(nodeId)}/timeseries?${queryString({ metric, range })}`),
  services: () => request<Record<string, any>>("/services"),
  serviceRuntime: () => request<Record<string, any>>("/services/runtime"),
  network: () => request<Record<string, any>>("/network"),
  storage: () => request<Record<string, any>>("/storage"),
  infrastructureSummary: () => request<Record<string, any>>("/infrastructure/summary"),
  metric: (name: string) => request<Record<string, any>>(`/metrics/${encodeURIComponent(name)}`),
  metricTimeseries: (name: string, range: OpsRange = "1h") => request<Record<string, any>>(`/metrics/${encodeURIComponent(name)}/timeseries?${queryString({ range })}`),
  database: (mode: DataMode = "REAL") => request<Record<string, any>>(`/database?data_mode=${mode}`),
  databaseHealth: () => request<Record<string, any>>("/database/health"),
  databaseTimeseries: (metric: "db_pool_checked_out" | "db_pool_idle", range: OpsRange = "1h") => request<Record<string, any>>(`/database/timeseries?${queryString({ metric, range })}`),
  queues: (mode: DataMode = "REAL") => request<Record<string, any>>(`/queues?data_mode=${mode}`),
  slo: (mode: DataMode = "REAL") => request<Record<string, any>>(`/slo?data_mode=${mode}`),
  sloWindows: (mode: DataMode = "REAL") => request<Record<string, any>>(`/slo/windows?data_mode=${mode}`),
  capacity: (mode: DataMode = "REAL") => request<Record<string, any>>(`/capacity?data_mode=${mode}`),
  capacityForecast: (range: "6h" | "24h" | "7d" | "30d" = "7d") => request<Record<string, any>>(`/capacity/forecast?range=${range}`),
  slowRoutes: (mode: DataMode = "REAL", limit = 25) => request<Record<string, any>>(`/routes/slow?${queryString({ data_mode: mode, limit })}`),
  errorRoutes: (mode: DataMode = "REAL", limit = 25) => request<Record<string, any>>(`/routes/errors?${queryString({ data_mode: mode, limit })}`),
  tenantHealth: (params: TenantHealthQuery) => request<Record<string, any>>(`/tenant-health?${queryString(params)}`),
  tenantHealthOne: (tenantId: string, mode: DataMode = "REAL") => request<Record<string, any>>(`/tenant-health/${encodeURIComponent(tenantId)}?data_mode=${mode}`),
  tenant360: (tenantId: string, mode: DataMode = "REAL") => request<Record<string, any>>(`/tenants/${encodeURIComponent(tenantId)}?data_mode=${mode}`),
  savedViews: (scope = "tenant_fleet") => request<Record<string, any>>(`/tenant-health/saved-views?scope=${encodeURIComponent(scope)}`),
  saveView: (payload: Record<string, any>) => request<Record<string, any>>("/tenant-health/saved-views", { method: "POST", body: JSON.stringify(payload) }),
  deleteSavedView: (id: string) => request<void>(`/tenant-health/saved-views/${encodeURIComponent(id)}`, { method: "DELETE" }),
  productRollups: (mode: DataMode = "REAL", days = 30) => request<Record<string, any>>(`/product-analytics/rollups?${queryString({ data_mode: mode, days })}`),
  users: (params: URLSearchParams) => request<Record<string, any>>(`/users?${params.toString()}`),
  incidentCenter: (params?: URLSearchParams) => request<Record<string, any>>(`/incident-center${params?.toString() ? `?${params.toString()}` : ""}`),
  incidentDetail: (id: string) => request<Record<string, any>>(`/incident-center/${encodeURIComponent(id)}`),
  createIncident: (payload: Record<string, any>) => request<Record<string, any>>("/incident-center", { method: "POST", body: JSON.stringify(payload) }),
  transitionIncident: (id: string, state: string, message: string) => request<Record<string, any>>(`/incident-center/${encodeURIComponent(id)}/transition`, { method: "POST", body: JSON.stringify({ state, message }) }),
  changeMarkers: (kind?: string) => request<Record<string, any>>(`/change-markers${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`),
  createChangeMarker: (payload: Record<string, any>) => request<Record<string, any>>("/change-markers", { method: "POST", body: JSON.stringify(payload) }),
  bulk: (payload: Record<string, any>) => request<Record<string, any>>("/operations/bulk", { method: "POST", body: JSON.stringify(payload) }),
  approve: (id: string, reason: string) => request<Record<string, any>>(`/operations/${encodeURIComponent(id)}/approve`, { method: "POST", body: JSON.stringify({ reason }) }),
  scheduleMaintenance: (payload: Record<string, any>) => request<Record<string, any>>("/changes/maintenance", { method: "POST", body: JSON.stringify(payload) }),
  queryRegistry: () => request<Record<string, any>>("/query-registry"),
};

export function operationsStreamUrl(mode: DataMode): string {
  return url(`/live?data_mode=${mode}`);
}
