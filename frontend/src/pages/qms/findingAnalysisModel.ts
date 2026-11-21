export type FindingInsights = {
  year: number; total: number; open: number; unmapped: number | null;
  groups: { key: string; total: number; open: number }[];
  months: { month: string; raised: number; closed: number }[];
};

const severityOrder: Record<string, number> = { CRITICAL: 0, MAJOR: 1, MINOR: 2 };
export function findingGroupLabel(key: string) {
  return key === "UNCLASSIFIED" ? "Not classified" : key.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase());
}
export function findingDistribution(data: FindingInsights, view: string, openOnly: boolean, search: string) {
  return data.groups.filter(group => (openOnly ? group.open : group.total) > 0
    && group.key.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => view === "by-severity"
      ? (severityOrder[a.key] ?? 3) - (severityOrder[b.key] ?? 3) || a.key.localeCompare(b.key)
      : (openOnly ? b.open - a.open : b.total - a.total) || a.key.localeCompare(b.key));
}
export function findingTrendSummary(months: FindingInsights["months"]) {
  const raised = months.reduce((sum, month) => sum + month.raised, 0);
  const closed = months.reduce((sum, month) => sum + month.closed, 0);
  // Closures can belong to earlier cohorts. This is an event balance, never
  // a closure rate or a historical backlog reconstructed from today's state.
  return { raised, closed, balance: raised - closed };
}
export const findingMonthLabel = (month: string) => new Intl.DateTimeFormat("en", { month: "short", timeZone: "UTC" }).format(new Date(`${month}-01T00:00:00Z`));
export const canFilterFindingSeverity = (key: string) => Object.hasOwn(severityOrder, key);
