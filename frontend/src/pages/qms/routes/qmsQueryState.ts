import { parseFindingLifecycleView, type FindingLifecycleView } from "../../qualityAudits/findingLifecycle";
import { qmsModulePath } from "./qmsRouteRegistry";

export type QmsView = "global" | "mine";
export type QmsRegisterFilters = {
  q: string; stage: FindingLifecycleView; timing: "" | "overdue" | "due_soon";
  auditId: string; level: string; status: "" | "open" | "closed";
  period?: number; view: QmsView; page: number; pageSize: 25 | 50 | 100;
};
export function parseQmsPeriod(value: string | null): number | undefined {
  const year = Number(value);
  return value && /^\d{4}$/.test(value) && year >= 2000 && year <= 2200 ? year : undefined;
}
export function parseQmsView(value: string | null): QmsView {
  return value === "mine" ? "mine" : "global";
}
export function parseQmsRegisterFilters(query: URLSearchParams): QmsRegisterFilters {
  const timing = query.get("timing");
  const status = query.get("status");
  const size = Number(query.get("pageSize"));
  const page = Number(query.get("page"));
  const rawLevel = query.get("level") || "";
  return {
    q: (query.get("q") || "").slice(0, 160), stage: parseFindingLifecycleView(query.get("stage")),
    timing: timing === "overdue" || timing === "due_soon" ? timing : "",
    auditId: query.get("auditId") || "",
    level: ["LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4"].includes(rawLevel) ? rawLevel : "",
    status: status === "open" || status === "closed" ? status : "",
    period: parseQmsPeriod(query.get("period")), view: parseQmsView(query.get("view")),
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    pageSize: size === 50 || size === 100 ? size : 25,
  };
}

/** Preserve only context a destination actually consumes. Never carry a drawer/page by accident. */
export function buildPreservedQmsQuery(current: URLSearchParams, patch: Record<string, string | number | null | undefined> = {}, keys: readonly string[] = ["view", "period"]): URLSearchParams {
  const next = new URLSearchParams();
  for (const key of keys) if (current.has(key)) next.set(key, current.get(key)!);
  for (const [key, value] of Object.entries(patch)) {
    if (value == null || value === "") next.delete(key);
    else next.set(key, String(value));
  }
  return next;
}
export function withQmsQuery(path: string, query: URLSearchParams): string {
  const [base, existing = ""] = path.split("?");
  const merged = new URLSearchParams(existing);
  query.forEach((value, key) => merged.set(key, value));
  return merged.size ? `${base}?${merged}` : base;
}
export function qmsRegisterPath(amoCode: string, filters: Partial<QmsRegisterFilters> = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value != null && value !== "" && value !== "all") query.set(key, String(value));
  }
  return withQmsQuery(qmsModulePath(amoCode, "audits", "register"), query);
}
