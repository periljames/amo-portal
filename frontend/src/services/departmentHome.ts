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

function waitForRetry(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return Promise.reject(new DOMException("Request was cancelled", "AbortError"));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", onAbort);
      callback();
    };
    const handle = window.setTimeout(() => finish(resolve), milliseconds);
    const onAbort = () => {
      window.clearTimeout(handle);
      finish(() => reject(new DOMException("Request was cancelled", "AbortError")));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * A route transition can briefly race backend/session readiness. Retry one
 * transient failure before showing the blocking workspace error; apiRequest
 * can still serve a tenant-scoped stale response when the network is down.
 */
export async function getDepartmentHome(
  amoCode: string,
  department: string,
  signal?: AbortSignal,
): Promise<DepartmentHomeResponse> {
  const path = `/auth/home/${encodeURIComponent(amoCode)}/${encodeURIComponent(department)}`;
  let lastError: unknown;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return await apiRequest<DepartmentHomeResponse>(path, {
        timeoutMs: 12_000,
        cacheTtlMs: 20_000,
        staleWhileOfflineMs: 20 * 60_000,
        persistCache: true,
        signal,
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      lastError = error;
      if (attempt === 0) await waitForRetry(350, signal);
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Department home could not be loaded.");
}
