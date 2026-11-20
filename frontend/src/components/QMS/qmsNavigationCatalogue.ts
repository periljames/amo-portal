import { QMS_ROUTE_REGISTRY, qmsBasePath, qmsModulePath } from "../../pages/qms/routes/qmsRouteRegistry";
import { QMS_WORKSPACES, qmsWorkspaceEntryPath, qmsPeopleWorkspacePath } from "../../pages/qms/routes/qmsWorkspaceRegistry";
import { qmsViewLabel } from "../../pages/qms/qmsWorkspaceCopy";

export type QualityDestination = { path: string; label: string; moduleLabel: string; section: string; permission: string; keywords: string };
export function qmsViewPermission(module: { id: string; permission: string }, view: string): string {
  return view === "new" ? module.id === "findings" ? "qms.finding.create" : module.permission.replace(/\.view$/, ".manage") : module.permission;
}
const workflowKeywords: Record<string, string> = {
  "management-review/meetings": "minutes agenda decisions chair attendees meeting",
  "management-review/dashboard": "briefing inputs performance management",
  "management-review/actions": "follow-up assignments verification completion evidence",
  "equipment-calibration/register": "tools instruments assets serial numbers",
  "equipment-calibration/calibration-history": "laboratory calibration results traceability",
  "system/quality-objectives": "kpi measures targets quality policy",
  "settings/audit-log": "history activity changes actor before after traceability",
};

/** One catalogue for menus and page search, derived from the route owners. */
export function qmsNavigationCatalogue(amoCode: string): QualityDestination[] {
  const destinations: QualityDestination[] = QMS_ROUTE_REGISTRY
    .filter(module => !["documents", "aerodoc"].includes(module.id))
    .flatMap(module => module.validViews.map(view => ({
      path: qmsModulePath(amoCode, module.id, view),
      label: view === module.defaultView ? module.navigationLabel : qmsViewLabel(view),
      moduleLabel: module.navigationLabel,
      section: module.section,
      permission: qmsViewPermission(module, view),
      keywords: `${module.label} ${module.navigationLabel} ${view} ${qmsViewLabel(view)} ${workflowKeywords[`${module.id}/${view}`] || ""}`.toLowerCase(),
    })));
  for (const [hub, label, permission] of [
    ["controls", "Control library", "qms.audit.view"],
    ["readiness", "Assurance readiness", "qms.dashboard.view"],
    ["evidence", "Control evidence", "qms.evidence.view"],
    ["intelligence", "Intelligence reviews", "qms.reports.view"],
  ]) destinations.push({ path: `${qmsBasePath(amoCode)}?hub=${hub}`, label,
    moduleLabel: "Assurance controls", section: "control", permission,
    keywords: `${label} assurance controls process mapping source verification approval effectiveness`.toLowerCase() });
  for (const workspace of QMS_WORKSPACES) {
    destinations.push({ path: qmsWorkspaceEntryPath(amoCode, workspace.id), label: workspace.label,
      moduleLabel: "Quality workspaces", section: "command", permission: workspace.permission,
      keywords: `${workspace.label} ${workspace.description}`.toLowerCase() });
  }
  destinations.push({ path: `${qmsBasePath(amoCode)}?workspace=assurance`, label: "Assurance cases",
    moduleLabel: "Assurance", section: "assurance", permission: "qms.audit.view",
    keywords: "assurance cases investigation causal conclusion root cause effectiveness verification" });
  for (const tab of ["overview", "people", "cases", "reviews", "administration"] as const) {
    destinations.push({ path: qmsPeopleWorkspacePath(amoCode, { tab }), label: qmsViewLabel(tab),
      moduleLabel: "People & authorizations", section: "command", permission: "qms.people.view",
      keywords: `people authorization appointments privileges cases reviews administration ${tab}` });
  }
  destinations.push({ path: `/maintenance/${encodeURIComponent(amoCode)}/document-control/library`, label: "Controlled documents",
    moduleLabel: "Document Control", section: "control", permission: "qms.document.view", keywords: "controlled documents library dms manuals" });
  // The QMS root is deliberately canonical for the overview.
  destinations.unshift({ path: qmsBasePath(amoCode), label: "Quality overview", moduleLabel: "Quality workspaces", section: "command", permission: "qms.dashboard.view", keywords: "overview home dashboard quality control room" });
  const paths = new Set<string>();
  return destinations.filter(item => !paths.has(item.path) && Boolean(paths.add(item.path)));
}

export function searchQualityDestinations(items: QualityDestination[], query: string): QualityDestination[] {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return items.filter(item => words.every(word => `${item.label} ${item.moduleLabel} ${item.keywords}`.toLowerCase().includes(word)));
}
