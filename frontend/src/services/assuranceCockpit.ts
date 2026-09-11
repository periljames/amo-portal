import { apiRequest, qualityPath } from "./apiClient";

export type AssuranceViewContext = "global" | "mine";
export type AssuranceRiskLevel = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type AssuranceCockpitPriority = {
  id: string;
  label: string;
  count: number;
  severity: AssuranceRiskLevel;
  why: string;
  path: string;
};

export type AssuranceCockpitDrilldown = {
  path: string;
  query?: Record<string, string>;
  drawer?: string;
};

export type AssuranceCockpitOverview = {
  tenant: { amo_code: string; amo_id: string };
  view: AssuranceViewContext;
  period: number;
  as_of: string;
  readiness: {
    score: number;
    band: "STRONG" | "WATCH" | "AT_RISK" | "CRITICAL";
    dimensions: Array<{ id: string; label: string; score: number; weight: number }>;
    method: string;
    disclaimer: string;
  };
  metrics: Record<string, number>;
  priority_queue: AssuranceCockpitPriority[];
  audit_pipeline: Array<{ status: string; count: number }>;
  finding_trend: Array<{
    month: string;
    level_1: number;
    level_2: number;
    level_3: number;
    observations: number;
    other: number;
  }>;
  closure_ageing: Array<{ bucket: string; count: number }>;
  control_exposure: Array<{ category: string; count: number }>;
  drilldowns: Record<string, AssuranceCockpitDrilldown>;
  scope: {
    mode: AssuranceViewContext;
    label: string;
    server_resolved_user: string | null;
    note: string;
  };
  warnings: Array<{ source: string; message: string; type: string }>;
};

export type AssuranceCommandResult = {
  kind: "action" | "audit" | "car" | "controlled_document" | "assurance_control" | string;
  id: string;
  reference?: string | null;
  title: string;
  subtitle?: string | null;
  status?: string | null;
  path: string;
};

export function getAssuranceCockpit(
  amoCode: string,
  options: { view: AssuranceViewContext; period: number },
): Promise<AssuranceCockpitOverview> {
  const params = new URLSearchParams({
    view: options.view,
    period: String(options.period),
  });
  return apiRequest<AssuranceCockpitOverview>(
    `${qualityPath(amoCode, "/excellence/cockpit")}?${params.toString()}`,
    { cacheTtlMs: 15_000, timeoutMs: 25_000 },
  );
}

export function searchAssuranceCommands(
  amoCode: string,
  query: string,
  limit = 20,
): Promise<{ items: AssuranceCommandResult[]; query: string; as_of: string; ranking?: string }> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return apiRequest(
    `${qualityPath(amoCode, "/excellence/command-search")}?${params.toString()}`,
    { cacheTtlMs: 5_000, timeoutMs: 15_000 },
  );
}

export function cockpitDrilldownHref(drilldown: AssuranceCockpitDrilldown | undefined): string | null {
  if (!drilldown) return null;
  const params = new URLSearchParams(drilldown.query || {});
  if (drilldown.drawer) params.set("drawer", drilldown.drawer);
  const query = params.toString();
  return query ? `${drilldown.path}?${query}` : drilldown.path;
}
