import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import {
  BrainCircuit,
  CalendarDays,
  ChevronDown,
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
    calendar: "Planner",
    audits: "Audit Assurance",
    findings: "Finding Assurance",
    cars: "Corrective Action",
    risk: "Risk Intelligence",
    "change-control": "Missions",
    system: "Quality System",
    documents: "Controlled Documents",
    suppliers: "Supplier Assurance",
    "equipment-calibration": "Tooling Assurance",
    "external-interface": "External Assurance",
    "management-review": "Management Review",
    reports: "Quality Intelligence",
    "evidence-vault": "Evidence Room",
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

  if (tab.queryTab) {
    return pathMatches(current, target) && (params.get("tab") || "war-room") === tab.queryTab;
  }
  if (tab.queryWorkspace) {
    const requested = params.get("workspace");
    const legacyHub = params.get("hub");
    const legacyWorkspace = legacyHub === "intelligence"
      ? "intelligence"
      : legacyHub === "controls" || legacyHub === "evidence"
        ? "assurance"
        : null;
    return current === target && (requested || legacyWorkspace) === tab.queryWorkspace;
  }
  if (tab.activePrefixes?.some((prefix) => pathMatches(current, prefix))) return true;
  if (tab.exact) {
    return current === target && !params.get("workspace") && !params.get("hub");
  }
  return pathMatches(current, target);
}

function topLevelTabs(route: QualityRoute): ContextTab[] {
  const workspaceItems = qmsWorkspaceNavigationItems(route.amoCode);
  const base = route.basePath;
  const activePrefixes: Record<QmsWorkspaceId, string[]> = {
    "control-room": [base],
    planner: [`${base}/planner`, `${base}/calendar`],
    missions: [`${base}/missions`, `${base}/change-control`],
    people: [`${base}/people`],
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
    queryWorkspace: ["missions", "people", "assurance", "intelligence"].includes(workspace.id) ? workspace.id : undefined,
    activePrefixes: workspace.id === "control-room" || ["missions", "people", "assurance", "intelligence"].includes(workspace.id)
      ? undefined
      : activePrefixes[workspace.id],
  }));
}

function auditSectionTabs(basePath: string): ContextTab[] {
  return [
    { id: "audit-overview", label: "Overview", path: `${basePath}/audits/dashboard`, exact: true },
    { id: "audit-programme", label: "Programme", path: `${basePath}/audits/program`, activePrefixes: [`${basePath}/audits/program`, `${basePath}/audits/programme`] },
    { id: "audit-schedule", label: "Schedule", path: `${basePath}/audits/plan?view=calendar`, activePrefixes: [`${basePath}/audits/plan`, `${basePath}/audits/schedule`, `${basePath}/audits/schedules`] },
    { id: "audit-register", label: "Active Audits", path: `${basePath}/audits/register`, exact: true },
    { id: "audit-checklists", label: "Checklists", path: `${basePath}/audits/checklists`, exact: true },
    { id: "audit-reports", label: "Reports", path: `${basePath}/audits/reports`, exact: true },
  ];
}

function auditRecordTabs(basePath: string, auditKey: string): ContextTab[] {
  const recordPath = `${basePath}/audits/${encodeURIComponent(auditKey)}`;
  return [
    { id: "audit-war-room", label: "War Room", path: `${recordPath}?tab=war-room`, queryTab: "war-room" },
    { id: "audit-checklist", label: "Checklist", path: `${recordPath}?tab=checklist`, queryTab: "checklist" },
    { id: "audit-findings", label: "Findings", path: `${recordPath}?tab=findings`, queryTab: "findings" },
    { id: "audit-cars", label: "CARs", path: `${recordPath}?tab=cars`, queryTab: "cars" },
    { id: "audit-evidence", label: "Evidence", path: `${recordPath}?tab=evidence`, queryTab: "evidence" },
    { id: "audit-report", label: "Report", path: `${recordPath}?tab=report`, queryTab: "report" },
    { id: "audit-closeout", label: "Closeout", path: `${recordPath}?tab=closeout`, queryTab: "closeout" },
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
      setMountTarget((current) => current === host ? current : host);
    };

    syncMount();
    const observer = new MutationObserver(syncMount);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      activeHost?.remove();
    };
  }, [qualityActive]);

  useEffect(() => {
    document.documentElement.classList.toggle("quality-context-active", qualityActive);
    const overview = Boolean(route && route.segments.length === 0);
    document.documentElement.classList.toggle("quality-context-overview", overview);
    return () => {
      document.documentElement.classList.remove("quality-context-active", "quality-context-overview");
    };
  }, [qualityActive, route]);

  if (!route || !mountTarget) return null;

  const [moduleSegment, recordKey] = route.segments;
  const safeRecordKey = recordKey || "";
  const isAuditRecord = moduleSegment === "audits" && Boolean(safeRecordKey) && !STATIC_AUDIT_VIEWS.has(safeRecordKey);
  const isCarRecord = moduleSegment === "cars" && Boolean(safeRecordKey) && !STATIC_CAR_VIEWS.has(safeRecordKey);
  const tabs = isAuditRecord
    ? auditRecordTabs(route.basePath, safeRecordKey)
    : isCarRecord
      ? carRecordTabs(route.basePath, safeRecordKey)
      : moduleSegment === "audits"
        ? auditSectionTabs(route.basePath)
        : topLevelTabs(route);

  const title = isAuditRecord
    ? `Audit ${safeRecordKey}`
    : isCarRecord
      ? `CAR ${safeRecordKey}`
      : moduleTitle(moduleSegment);

  const defaultWorkPath = `${route.basePath}/inbox/assigned-to-me`;
  const primaryAction = isAuditRecord
    ? { label: "Audit register", path: `${route.basePath}/audits/register`, icon: ClipboardCheck }
    : isCarRecord
      ? { label: "CAR register", path: `${route.basePath}/cars/register`, icon: ListChecks }
      : moduleSegment === "findings"
        ? { label: "New finding", path: `${route.basePath}/findings/new`, icon: Plus }
        : moduleSegment === "cars"
          ? { label: "Create CAR", path: `${route.basePath}/cars/new`, icon: Plus }
          : moduleSegment === "change-control"
            ? { label: "New mission", path: `${route.basePath}/change-control/new`, icon: Plus }
            : { label: "My work", path: defaultWorkPath, icon: ListChecks };

  const PrimaryIcon = primaryAction.icon;

  return createPortal(
    <section className="quality-context-bar" aria-label="Quality Assurance workspace navigation">
      <div className="quality-context-bar__identity">
        <span className="quality-context-bar__mark"><ShieldCheck size={17} aria-hidden="true" /></span>
        <span><small>Quality assurance</small><strong>{title}</strong></span>
      </div>

      <nav className="quality-context-bar__tabs" aria-label={`${title} related pages`}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const active = tabIsActive(tab, location.pathname, location.search);
          return (
            <button key={tab.id} type="button" className={active ? "is-active" : ""} aria-current={active ? "page" : undefined} onClick={() => navigate(tab.path)}>
              {Icon ? <Icon size={15} aria-hidden="true" /> : null}<span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="quality-context-bar__actions">
        <span className="quality-context-bar__live" title="Quality data refreshes while the workspace is active"><RefreshCw size={13} aria-hidden="true" /> Live</span>
        <button type="button" className="quality-context-bar__primary" onClick={() => navigate(primaryAction.path)}><PrimaryIcon size={15} aria-hidden="true" /><span>{primaryAction.label}</span></button>
        <details className="quality-context-bar__more">
          <summary aria-label="Open Quality assurance lenses"><MoreHorizontal size={17} /><ChevronDown size={13} /></summary>
          <div>
            <strong>Assurance lenses</strong>
            <button type="button" onClick={() => navigate(`${route.basePath}/audits/dashboard`)}>Audits & surveillance</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/findings/register`)}>Findings</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/cars/register`)}>Corrective action</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/suppliers/approved-list`)}>Supplier assurance</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/equipment-calibration/overdue`)}>Tooling exposure</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/risk/risk-matrix`)}>Risk intelligence</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/management-review/dashboard`)}>Management review</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/evidence-vault/search`)}>Evidence room</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/settings/general`)}>QMS settings</button>
          </div>
        </details>
      </div>
    </section>,
    mountTarget,
  );
};

export default QualityContextTabs;
