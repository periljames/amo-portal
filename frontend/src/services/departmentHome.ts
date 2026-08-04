import { apiRequest } from "./apiClient";

export type DepartmentHomeTask = {
  id: string;
  title: string;
  description?: string | null;
  priority: number;
  status: string;
  due_at?: string | null;
  route: string;
  entity_type?: string | null;
  entity_id?: string | null;
};

export type DepartmentHomeAlert = {
  id: string;
  tone: "danger" | "warning" | "positive" | "neutral";
  title: string;
  message: string;
  route: string;
};

export type DepartmentHomeActivity = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  occurred_at: string;
};

export type DepartmentHomeQuickAction = {
  id: string;
  label: string;
  description: string;
  route: string;
};

export type DepartmentHomeResponse = {
  contract: "department-home.v1";
  amo: { id: string; code: string; slug: string; name: string };
  department: string;
  generated_at: string;
  summary: {
    assigned_open: number;
    approvals_open: number;
    overdue: number;
    due_soon: number;
    high_priority: number;
  };
  alerts: DepartmentHomeAlert[];
  assigned_work: DepartmentHomeTask[];
  approvals: DepartmentHomeTask[];
  schedule: DepartmentHomeTask[];
  recent_activity: DepartmentHomeActivity[];
  quick_actions: DepartmentHomeQuickAction[];
  news: Array<{ id: string; title: string; message: string; published_at?: string | null }>;
  source_health: Record<string, "healthy" | "degraded" | "not_configured">;
};

export function getDepartmentHome(
  amoCode: string,
  department: string,
  signal?: AbortSignal,
): Promise<DepartmentHomeResponse> {
  return apiRequest<DepartmentHomeResponse>(
    `/auth/home/${encodeURIComponent(amoCode)}/${encodeURIComponent(department)}`,
    {
      timeoutMs: 12_000,
      cacheTtlMs: 20_000,
      staleWhileOfflineMs: 20 * 60_000,
      persistCache: true,
      signal,
    },
  );
}
