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
    score: number | null;
    band: "STRONG" | "WATCH" | "AT_RISK" | "CRITICAL" | "UNAVAILABLE";
    dimensions: Array<{ id: string; label: string; score: number | null; weight: number }>;
    method: string;
    disclaimer: string;
  };
  metrics: Record<string, number | null>;
  priority_queue: AssuranceCockpitPriority[];
  audit_pipeline: Array<{ status: string; count: number }> | null;
  finding_trend: Array<{
    month: string;
    level_1: number;
    level_2: number;
    level_3: number;
    observations: number;
    other: number;
  }> | null;
  closure_ageing: Array<{ bucket: string; count: number }> | null;
  control_exposure: Array<{ category: string; count: number }> | null;
  drilldowns: Record<string, AssuranceCockpitDrilldown>;
  scope: {
    mode: AssuranceViewContext;
    label: string;
    server_resolved_user: string | null;
    note: string;
  };
  source_health: "SUCCESS" | "PARTIAL";
  metric_basis: Record<string, "PERIOD_EVENT" | "PERIOD_DUE" | "AS_OF_CURRENT">;
  period_note: string;
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

export type UnscheduledProgrammeRequirement = {
  id: string;
  programme_id: string;
  programme_ref: string;
  programme_title: string;
  title: string;
  audit_type: string;
  mandatory_surveillance: boolean;
  target_start: string | null;
  target_end: string | null;
  default_duration_days: number;
  default_location: string | null;
  lead_auditor_user_id: string | null;
  observer_auditor_user_id: string | null;
  auditee_user_id: string | null;
  state: string;
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

export async function getUnscheduledProgrammeRequirements(
  amoCode: string,
  options: { view: AssuranceViewContext; period: number; limit?: number },
): Promise<{ items: UnscheduledProgrammeRequirement[]; total_returned: number; total: number;
  view: AssuranceViewContext; period: number; planner_path: string; programme_path: string }> {
  const items: UnscheduledProgrammeRequirement[] = [];
  let offset = 0;
  while (true) {
    const params = new URLSearchParams({ view: options.view, period: String(options.period), limit: String(options.limit ?? 100), offset: String(offset) });
    const page = await apiRequest<{ items: UnscheduledProgrammeRequirement[]; total: number;
      view: AssuranceViewContext; period: number; planner_path: string; programme_path: string }>(
      `${qualityPath(amoCode, "/excellence/cockpit/unscheduled-requirements")}?${params}`, { cacheTtlMs: 0, timeoutMs: 20_000 });
    items.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total) return { ...page, items, total_returned: items.length };
    if (!page.items.length) throw new Error("Programme changed during pagination; refresh and retry.");
  }
}

export function searchAssuranceCommands(
  amoCode: string,
  query: string,
  limit = 20,
  view: AssuranceViewContext = "global",
): Promise<{ items: AssuranceCommandResult[]; query: string; as_of: string; ranking?: string; warnings?: Array<{ source: string; message: string; type: string }> }> {
  const params = new URLSearchParams({ q: query, limit: String(limit), view });
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
