import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import {
  BrainCircuit,
  CalendarDays,
  ClipboardCheck,
  FolderKanban,
  Gauge,
  ListChecks,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserRoundCheck,
  type LucideIcon,
} from "lucide-react";

import { qmsBasePath, qmsModulePath, qmsRecordPath, qmsRouteWorkspace, QMS_ROUTE_REGISTRY, AUDIT_ASSURANCE_DESTINATIONS } from "../../pages/qms/routes/qmsRouteRegistry";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { qmsWorkspaceNavigationItems, QMS_WORKSPACES, type QmsWorkspaceId } from "../../pages/qms/routes/qmsWorkspaceRegistry";

type ContextTab = {
  id: string;
  label: string;
  path: string;
  icon?: LucideIcon;
  exact?: boolean;
  queryTab?: string;
  queryWorkspace?: QmsWorkspaceId;
  activePrefixes?: string[];
  excludePrefixes?: string[];
};

type QualityRoute = {
  amoCode: string;
  basePath: string;
  segments: string[];
};

const STATIC_AUDIT_VIEWS = new Set([...(QMS_ROUTE_REGISTRY.find((module) => module.id === "audits")?.validViews || []), "schedules"]);
const STATIC_CAR_VIEWS = new Set(QMS_ROUTE_REGISTRY.find((module) => module.id === "cars")?.validViews || []);
const ASSURANCE_MODULES = new Set(QMS_ROUTE_REGISTRY.filter((module) => qmsRouteWorkspace(module.segment) === "assurance").map((module) => module.segment));
const AUDIT_ASSURANCE_SEGMENTS = new Set(["audits", "findings"]);

const WORKSPACE_ICONS: Record<QmsWorkspaceId, LucideIcon> = {
  "control-room": Gauge,
  planner: CalendarDays,
  missions: FolderKanban,
  people: UserRoundCheck,
  assurance: ShieldCheck,
  intelligence: BrainCircuit,
};

function parseQualityRoute(pathname: string): QualityRoute | null {
  const qualityMatch = pathname.match(/^\/maintenance\/([^/]+)\/quality(?:\/(.*))?$/i);
  if (!qualityMatch) return null;
  const amoCode = decodeURIComponent(qualityMatch[1]);
  return {
    amoCode,
    basePath: qmsBasePath(amoCode),
    segments: (qualityMatch[2] || "").split("/").filter(Boolean).map((segment) => decodeURIComponent(segment)),
  };
}

function moduleTitle(segment: string | undefined): string {
  if (!segment) return "Control Room";
  return QMS_ROUTE_REGISTRY.find((module) => module.segment === segment)?.label || "Control Room";
}

function pathMatches(current: string, target: string): boolean {
  const cleanTarget = target.split("?")[0].replace(/\/$/, "");
  return current === cleanTarget || current.startsWith(`${cleanTarget}/`);
}

function tabIsActive(tab: ContextTab, pathname: string, search: string): boolean {
  const target = tab.path.split("?")[0].replace(/\/$/, "");
  const current = pathname.replace(/\/$/, "");
  const params = new URLSearchParams(search);

  if (tab.excludePrefixes?.some((prefix) => pathMatches(current, prefix))) return false;

  if (tab.queryTab) {
    return pathMatches(current, target) && (params.get("tab") || "war-room") === tab.queryTab;
  }

  if (tab.queryWorkspace) {
    if (current === target) return params.get("workspace") === tab.queryWorkspace;
    return Boolean(tab.activePrefixes?.some((prefix) => pathMatches(current, prefix)));
  }

  if (tab.activePrefixes?.some((prefix) => pathMatches(current, prefix))) return true;
  if (tab.exact) return current === target && !params.get("workspace");
  return current === target;
}

function topLevelTabs(route: QualityRoute): ContextTab[] {
  const workspaceItems = qmsWorkspaceNavigationItems(route.amoCode);
  const base = route.basePath;

  return workspaceItems.filter((workspace) => hasQmsRolePermission(workspace.permission)).map((workspace) => ({
    id: workspace.id,
    label: workspace.shortLabel,
    path: workspace.path,
    icon: WORKSPACE_ICONS[workspace.id],
    exact: workspace.id === "control-room",
    // Assurance lands on /audits/dashboard — do not require ?workspace=assurance for active state.
    queryWorkspace: ["missions", "people", "intelligence"].includes(workspace.id) ? workspace.id : undefined,
    activePrefixes: workspace.activePrefixes.map((prefix) => `${base}/${prefix}`),
    excludePrefixes: workspace.id === "intelligence" ? [`${base}/reports/car-performance`] : undefined,
  }));
}

function activeWorkspaceId(
  route: QualityRoute,
  pathname: string,
  search: string,
): QmsWorkspaceId | null {
  const tabs = topLevelTabs(route);
  const active = tabs.find((tab) => tabIsActive(tab, pathname, search));
  return (active?.id as QmsWorkspaceId | undefined) || null;
}

function workspaceTitle(workspace: QmsWorkspaceId | null, moduleSegment: string | undefined): string {
  if (workspace) {
    const definition = QMS_WORKSPACES.find((item) => item.id === workspace);
    if (definition) return definition.label;
  }
  if (moduleSegment === "calendar") return "Planner";
  return moduleTitle(moduleSegment);
}

/**
 * Permanent Assurance related-pages.
 * When Audit Assurance rail owns Overview/Plan/Audits/Findings, do not render a
 * second permanent related-pill row — demote sibling products into Tools.
 */
function assurancePrimaryTabs(amoCode: string, railOwnsNav: boolean): ContextTab[] {
  if (railOwnsNav) return [];
  return AUDIT_ASSURANCE_DESTINATIONS.filter((destination) => ["dashboard", "programme", "audits", "findings-actions", "evidence"].includes(destination.id) && hasQmsRolePermission(destination.permission)).map((destination) => {
    const [module, view] = destination.relativePath.split("/");
    return { id: destination.id, label: destination.shortLabel, path: qmsModulePath(amoCode, module, view),
      activePrefixes: (destination.activePrefixes || destination.activeExact || []).map((prefix) => `${qmsBasePath(amoCode)}/${prefix}`) };
  });
}

function carRecordTabs(amoCode: string, carKey: string): ContextTab[] {
  const recordPath = qmsRecordPath(amoCode, "cars", carKey);
  return [
    { id: "car-overview", label: "Overview", path: `${recordPath}/overview`, exact: true },
    { id: "car-containment", label: "Containment", path: `${recordPath}/containment`, exact: true },
    { id: "car-root-cause", label: "Root Cause", path: `${recordPath}/root-cause`, exact: true },
    { id: "car-actions", label: "Actions", path: `${recordPath}/actions`, exact: true },
    { id: "car-evidence", label: "Evidence", path: `${recordPath}/evidence`, exact: true },
    { id: "car-review", label: "Review", path: `${recordPath}/review`, exact: true },
    { id: "car-effectiveness", label: "Effectiveness", path: `${recordPath}/effectiveness`, exact: true },
    { id: "car-closeout", label: "Closeout", path: `${recordPath}/closeout`, exact: true },
  ];
}

const QualityContextTabs: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const route = useMemo(() => parseQualityRoute(location.pathname), [location.pathname]);
  const qualityActive = Boolean(route);
  const [mountTarget, setMountTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (!qualityActive) {
      document.querySelector(".quality-context-bar-host")?.remove();
      return;
    }

    let activeHost: HTMLDivElement | null = null;
    const syncMount = () => {
      const main = document.querySelector<HTMLElement>(".tenant-shell__main");
      if (!main) {
        if (activeHost && !activeHost.isConnected) activeHost = null;
        setMountTarget(null);
        return;
      }
      let host = main.querySelector<HTMLDivElement>(":scope > .quality-context-bar-host");
      if (!host) {
        host = document.createElement("div");
        host.className = "quality-context-bar-host";
        main.prepend(host);
      }
      activeHost = host;
      setMountTarget((current) => (current === host ? current : host));
    };

    // The tenant shell currently exposes only .tenant-shell__main; no stable portal slot exists.
    syncMount();
    const observer = new MutationObserver(syncMount);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      activeHost?.remove();
    };
  }, [qualityActive]);

  const moduleSegmentPreview = route?.segments[0];
  const aaRailOwnsLocalNav = Boolean(
    moduleSegmentPreview &&
      (AUDIT_ASSURANCE_SEGMENTS.has(moduleSegmentPreview) || moduleSegmentPreview === "evidence-vault" || route?.segments.join("/") === "reports/car-performance"),
  );

  useEffect(() => {
    document.documentElement.classList.toggle("quality-context-active", qualityActive);
    const overview = Boolean(route && route.segments.length === 0);
    document.documentElement.classList.toggle("quality-context-overview", overview);
    document.documentElement.classList.toggle("audit-assurance-surface", qualityActive && aaRailOwnsLocalNav);
    return () => {
      document.documentElement.classList.remove(
        "quality-context-active",
        "quality-context-overview",
        "audit-assurance-surface",
      );
    };
  }, [aaRailOwnsLocalNav, qualityActive, route]);

  if (!route || !mountTarget) return null;

  const [moduleSegment, recordKey] = route.segments;
  const safeRecordKey = recordKey || "";
  const workspace = new URLSearchParams(location.search).get("workspace");
  const isAuditRecord = moduleSegment === "audits" && Boolean(safeRecordKey) && !STATIC_AUDIT_VIEWS.has(safeRecordKey);
  const isCarRecord = moduleSegment === "cars" && Boolean(safeRecordKey) && !STATIC_CAR_VIEWS.has(safeRecordKey);
  const isAssuranceHub = !moduleSegment && workspace === "assurance";
  const isAssuranceModule = Boolean(moduleSegment && ASSURANCE_MODULES.has(moduleSegment));
  // Calendar is planner-owned for related/tools chrome; AA section layout may still wrap it.
  const isAuditAssuranceSurface =
    moduleSegment === "audits" || moduleSegment === "evidence-vault";
  const showAssuranceRelated =
    isAuditAssuranceSurface || isAssuranceHub || isAssuranceModule || isAuditRecord;

  const workspaceTabs = topLevelTabs(route);
  const assurancePrimary = assurancePrimaryTabs(route.amoCode, aaRailOwnsLocalNav);

  // Audit occurrence stages are owned by AuditLifecycleRail — do not duplicate Setup/Prepare/… pills here.
  const contextualTabs = isCarRecord
    ? carRecordTabs(route.amoCode, safeRecordKey)
    : showAssuranceRelated
      ? assurancePrimary
      : [];

  const title = isAuditRecord
    ? "Audits"
    : isCarRecord
      ? `CAR ${safeRecordKey}`
      : workspaceTitle(activeWorkspaceId(route, location.pathname, location.search), moduleSegment);

  const currentWorkspace = activeWorkspaceId(route, location.pathname, location.search);
  const defaultWorkPath = `${route.basePath}/inbox/assigned-to-me`;
  const primaryAction = isAuditRecord
    ? { label: "Audits overview", path: `${route.basePath}/audits/dashboard`, icon: ClipboardCheck }
    : isCarRecord
      ? { label: "CAR register", path: `${route.basePath}/cars/register`, icon: ListChecks }
      : moduleSegment === "findings"
        ? { label: "New finding", path: `${route.basePath}/findings/new`, icon: Plus }
        : moduleSegment === "cars"
          ? { label: "Create CAR", path: `${route.basePath}/cars/new`, icon: Plus }
          : moduleSegment === "change-control"
            ? { label: "New mission", path: `${route.basePath}?workspace=missions`, icon: Plus }
            : { label: "My work", path: defaultWorkPath, icon: ListChecks };

  const PrimaryIcon = primaryAction.icon;

  const renderTabs = (tabs: ContextTab[]) =>
    tabs.map((tab) => {
      const Icon = tab.icon;
      const active = tabIsActive(tab, location.pathname, location.search);
      return (
        <button
          key={tab.id}
          type="button"
          className={active ? "is-active" : ""}
          aria-current={active ? "page" : undefined}
          data-preload-route={tab.path}
          onClick={() => navigate(tab.path)}
        >
          {Icon ? <Icon size={15} aria-hidden="true" /> : null}
          <span>{tab.label}</span>
        </button>
      );
    });

  const calendarSurface = moduleSegment === "calendar" || currentWorkspace === "planner";
  const IdentityMark = currentWorkspace
    ? WORKSPACE_ICONS[currentWorkspace]
    : calendarSurface
      ? CalendarDays
      : ShieldCheck;

  return createPortal(
    <section className="quality-context-bar" aria-label="Quality Assurance workspace navigation">
      <div className="quality-context-bar__identity">
        <span className={`quality-context-bar__mark${calendarSurface ? " quality-context-bar__mark--calendar" : ""}`}>
          <IdentityMark size={17} aria-hidden="true" />
        </span>
        <span>
          <small>{calendarSurface || currentWorkspace === "assurance" ? "Quality" : "Quality assurance"}</small>
          {isAuditRecord ? (
            <span className="quality-context-bar__title">{title}</span>
          ) : (
            <h1 className="quality-context-bar__title">{title}</h1>
          )}
        </span>
      </div>

      <nav className="quality-context-bar__tabs" aria-label="Quality Assurance workspaces">
        {renderTabs(workspaceTabs)}
      </nav>

      <div className="quality-context-bar__actions">
        <span className="quality-context-bar__live" title="Quality data refreshes while the workspace is active">
          <RefreshCw size={13} aria-hidden="true" /> Live
        </span>
        {!aaRailOwnsLocalNav || isAuditRecord ? (
          <button type="button" className="quality-context-bar__primary" onClick={() => navigate(primaryAction.path)}>
            <PrimaryIcon size={15} aria-hidden="true" />
            <span>{primaryAction.label}</span>
          </button>
        ) : null}
      </div>

      {contextualTabs.length > 0 ? (
        <nav className="quality-context-bar__subtabs" aria-label={`${title} related pages`}>
          {renderTabs(contextualTabs)}
        </nav>
      ) : null}
    </section>,
    mountTarget,
  );
};

export default QualityContextTabs;
