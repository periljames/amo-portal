// src/services/adminOverview.ts
import { apiGet } from "./crs";
import { authHeaders } from "./auth";

export type OverviewSystemStatus = {
  status: "healthy" | "degraded" | "down";
  last_checked_at: string;
  refresh_paused: boolean;
  errors: string[];
};

export type OverviewBadge = {
  count?: number | null;
  severity: "critical" | "warning" | "info";
  route: string;
  available: boolean;
};

export type OverviewIssue = {
  key: string;
  label: string;
  count?: number | null;
  severity: "critical" | "warning" | "info";
  route: string;
};

export type OverviewActivity = {
  occurred_at?: string | null;
  action: string;
  entity_type: string;
  actor_user_id?: string | null;
};

export type OverviewSummary = {
  system: OverviewSystemStatus;
  badges: Record<string, OverviewBadge>;
  issues: OverviewIssue[];
  recent_activity: OverviewActivity[];
  recent_activity_available: boolean;
};

function uniqueRecentActivity(items: OverviewActivity[]): OverviewActivity[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = [
      item.occurred_at || "",
      item.action,
      item.entity_type,
      item.actor_user_id || "system",
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export async function fetchOverviewSummary(opts?: { silent?: boolean }): Promise<OverviewSummary> {
  const response = await apiGet<OverviewSummary>("/accounts/admin/overview-summary", {
    headers: authHeaders(),
    silent: opts?.silent ?? false,
  });
  return {
    ...response,
    recent_activity: uniqueRecentActivity(response.recent_activity || []),
  };
}
