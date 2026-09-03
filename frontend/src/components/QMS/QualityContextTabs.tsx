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
  MoreHorizontal,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserRoundCheck,
  type LucideIcon,
} from "lucide-react";

import { qmsWorkspaceNavigationItems, type QmsWorkspaceId } from "../../pages/qms/routes/qmsWorkspaceRegistry";

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

const STATIC_AUDIT_VIEWS = new Set([
  "dashboard",
  "program",
  "programme",
  "schedule",
  "plan",
  "register",
  "checklists",
  "reports",
  "templates",
  "new",
  "bin",
  "schedules",
]);

const STATIC_CAR_VIEWS = new Set([
  "register",
  "new",
  "overdue",
  "due-soon",
  "awaiting-auditee",
  "awaiting-quality-review",
  "awaiting-effectiveness-review",
  "closed",
]);

const ASSURANCE_MODULES = new Set([
  "findings",
  "cars",
  "suppliers",
  "equipment-calibration",
  "external-interface",
  "evidence-vault",
]);

/** Surfaces where the Audits rail owns local nav (calendar stays planner-owned). */
const AUDIT_ASSURANCE_SEGMENTS = new Set(["audits"]);

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
    basePath: `/maintenance/${encodeURIComponent(amoCode)}/quality`,
    segments: (qualityMatch[2] || "").split("/").filter(Boolean).map((segment) => decodeURIComponent(segment)),
  };
}

function moduleTitle(segment: string | undefined): string {
  const labels: Record<string, string> = {
    calendar: "Calendar",
    audits: "Audits",
    findings: "Findings",
    cars: "Corrective Action",
    risk: "Risk Intelligence",
    "change-control": "Missions",
    system: "Quality System",
    documents: "Controlled Documents",
    suppliers: "External Providers",
    "equipment-calibration": "Tooling Assurance",
    "external-interface": "External & Regulatory",
    "management-review": "Management Review",
    reports: "Quality Intelligence",
    "evidence-vault": "Evidence",
    settings: "QMS Settings",
    aerodoc: "AeroDoc",
  };
  return segment ? labels[segment] || segment.replaceAll("-", " ") : "Quality Assurance";
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
  if (tab.exact) return current === target && !params.get("workspace") && !params.get("hub");
  return current === target;
}

function topLevelTabs(route: QualityRoute): ContextTab[] {
  const workspaceItems = qmsWorkspaceNavigationItems(route.amoCode);
  const base = route.basePath;

  const activePrefixes: Record<QmsWorkspaceId, string[] | undefined> = {
    "control-room": undefined,
    planner: [`${base}/planner`, `${base}/calendar`],
    missions: [`${base}/missions`, `${base}/change-control`],
    people: [`${base}/people`],
    // Assurance owns audits + assurance cases + findings/CAR/providers family.
    // Calendar stays planner-owned — do not dual-activate Assurance on /calendar.
    assurance: [
      `${base}/assurance`,
      `${base}/audits`,
      `${base}/findings`,
      `${base}/cars`,
      `${base}/suppliers`,
      `${base}/equipment-calibration`,
      `${base}/external-interface`,
      `${base}/evidence-vault`,
    ],
    intelligence: [
      `${base}/intelligence`,
      `${base}/risk`,
      `${base}/management-review`,
      `${base}/reports`,
      `${base}/system`,
    ],
  };

  return workspaceItems.map((workspace) => ({
    id: workspace.id,
    label: workspace.shortLabel,
    path: workspace.path,
    icon: WORKSPACE_ICONS[workspace.id],
    exact: workspace.id === "control-room",
    // Assurance lands on /audits/dashboard — do not require ?workspace=assurance for active state.
    queryWorkspace: ["missions", "people", "intelligence"].includes(workspace.id) ? workspace.id : undefined,
    activePrefixes: workspace.id === "control-room" ? undefined : activePrefixes[workspace.id],
  }));
}

/**
 * Permanent Assurance related-pages.
 * When Audit Assurance rail owns Overview/Plan/Audits/Findings, do not render a
 * second permanent related-pill row — demote sibling products into Tools.
 */
function assurancePrimaryTabs(basePath: string, aaRailOwnsLocalNav: boolean): ContextTab[] {
  if (aaRailOwnsLocalNav) {
    return [];
  }

  return [
    {
      id: "assurance-audits",
      label: "Audits",
      path: `${basePath}/audits/dashboard`,
      activePrefixes: [`${basePath}/audits`],
      excludePrefixes: [`${basePath}/audits/register`, `${basePath}/audits/findings-actions`],
    },
    {
      id: "assurance-home",
      label: "Assurance cases",
      path: `${basePath}?workspace=assurance`,
      queryWorkspace: "assurance",
    },
    {
      id: "assurance-findings",
      label: "Findings & Actions",
      path: `${basePath}/audits/register?tab=findings`,
      activePrefixes: [`${basePath}/findings`, `${basePath}/audits/register`],
    },
    {
      id: "assurance-cars",
      label: "Corrective action",
      path: `${basePath}/cars/register`,
      activePrefixes: [`${basePath}/cars`],
    },
    {
      id: "assurance-evidence",
      label: "Evidence",
      path: `${basePath}/evidence-vault/search`,
      activePrefixes: [`${basePath}/evidence-vault`],
    },
  ];
}

/** Demoted assurance destinations — overflow/tools only. */
function assuranceToolTabs(basePath: string, aaRailOwnsLocalNav: boolean): ContextTab[] {
  const demotedOnAa: ContextTab[] = aaRailOwnsLocalNav
    ? [
        {
          id: "assurance-home",
          label: "Assurance cases",
          path: `${basePath}?workspace=assurance`,
          queryWorkspace: "assurance",
          // Exact hub only — do not light Assurance cases while browsing Audits surfaces.
          exact: true,
        },
        {
          id: "assurance-cars",
          label: "Corrective action",
          path: `${basePath}/cars/register`,
          activePrefixes: [`${basePath}/cars`],
        },
        {
          id: "assurance-evidence",
          label: "Evidence",
          path: `${basePath}/evidence-vault/search`,
          activePrefixes: [`${basePath}/evidence-vault`],
        },
      ]
    : [];

  return [
    ...demotedOnAa,
    {
      id: "assurance-providers",
      label: "External providers",
      path: `${basePath}/suppliers/approved-list`,
      activePrefixes: [`${basePath}/suppliers`],
    },
    {
      id: "assurance-tooling",
      label: "Tooling",
      path: `${basePath}/equipment-calibration/register`,
      activePrefixes: [`${basePath}/equipment-calibration`],
    },
    {
      id: "assurance-external",
      label: "External & regulatory",
      path: `${basePath}/external-interface/regulator-findings`,
      activePrefixes: [`${basePath}/external-interface`],
    },
  ];
}

function carRecordTabs(basePath: string, carKey: string): ContextTab[] {
  const recordPath = `${basePath}/cars/${encodeURIComponent(carKey)}`;
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
      (AUDIT_ASSURANCE_SEGMENTS.has(moduleSegmentPreview) || moduleSegmentPreview === "evidence-vault"),
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
  const assurancePrimary = assurancePrimaryTabs(route.basePath, aaRailOwnsLocalNav);
  const assuranceTools = assuranceToolTabs(route.basePath, aaRailOwnsLocalNav);
  const toolsActive = assuranceTools.some((tab) => tabIsActive(tab, location.pathname, location.search));

  // Audit occurrence stages are owned by AuditLifecycleRail — do not duplicate Setup/Prepare/… pills here.
  const contextualTabs = isCarRecord
    ? carRecordTabs(route.basePath, safeRecordKey)
    : showAssuranceRelated
      ? assurancePrimary
      : [];

  const title = isAuditRecord
    ? "Audits"
    : isCarRecord
      ? `CAR ${safeRecordKey}`
      : isAssuranceHub
        ? "Assurance"
        : moduleSegment === "calendar"
          ? "Calendar"
          : isAuditAssuranceSurface && moduleSegment === "audits"
            ? "Audits"
            : moduleTitle(moduleSegment);

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
          onClick={() => navigate(tab.path)}
        >
          {Icon ? <Icon size={15} aria-hidden="true" /> : null}
          <span>{tab.label}</span>
        </button>
      );
    });

  const renderAssuranceToolsMenu = () => (
    <details className={`quality-context-bar__more${toolsActive ? " is-active" : ""}`}>
      <summary aria-label="Assurance tools">
        <MoreHorizontal size={16} aria-hidden="true" />
        <span>Tools</span>
      </summary>
      <div role="menu">
        {assuranceTools.map((tab) => {
          const active = tabIsActive(tab, location.pathname, location.search);
          return (
            <button
              key={tab.id}
              type="button"
              role="menuitem"
              className={active ? "is-active" : ""}
              aria-current={active ? "page" : undefined}
              onClick={() => navigate(tab.path)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </details>
  );

  const calendarSurface = moduleSegment === "calendar";
  const IdentityMark = calendarSurface ? CalendarDays : ShieldCheck;

  return createPortal(
    <section className="quality-context-bar" aria-label="Quality Assurance workspace navigation">
      <div className="quality-context-bar__identity">
        <span className={`quality-context-bar__mark${calendarSurface ? " quality-context-bar__mark--calendar" : ""}`}>
          <IdentityMark size={17} aria-hidden="true" />
        </span>
        <span>
          <small>{calendarSurface ? "Quality" : "Quality assurance"}</small>
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
        {showAssuranceRelated && !isCarRecord && contextualTabs.length === 0 ? renderAssuranceToolsMenu() : null}
        <button type="button" className="quality-context-bar__primary" onClick={() => navigate(primaryAction.path)}>
          <PrimaryIcon size={15} aria-hidden="true" />
          <span>{primaryAction.label}</span>
        </button>
      </div>

      {contextualTabs.length > 0 ? (
        <nav className="quality-context-bar__subtabs" aria-label={`${title} related pages`}>
          {renderTabs(contextualTabs)}
          {showAssuranceRelated && !isCarRecord ? renderAssuranceToolsMenu() : null}
        </nav>
      ) : null}
    </section>,
    mountTarget,
  );
};

export default QualityContextTabs;
