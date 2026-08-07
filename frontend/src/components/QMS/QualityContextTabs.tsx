import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import {
  CalendarDays,
  ChevronDown,
  ClipboardCheck,
  Gauge,
  Inbox,
  ListChecks,
  MoreHorizontal,
  Plus,
  RefreshCw,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";


type ContextTab = {
  id: string;
  label: string;
  path: string;
  icon?: LucideIcon;
  exact?: boolean;
  queryTab?: string;
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

function parseQualityRoute(pathname: string): QualityRoute | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)\/quality(?:\/(.*))?$/i);
  if (!match) return null;
  const amoCode = decodeURIComponent(match[1]);
  return {
    amoCode,
    basePath: `/maintenance/${encodeURIComponent(amoCode)}/quality`,
    segments: (match[2] || "").split("/").filter(Boolean).map((segment) => decodeURIComponent(segment)),
  };
}

function moduleTitle(segment: string | undefined): string {
  const labels: Record<string, string> = {
    inbox: "My Quality Work",
    calendar: "QMS Calendar",
    audits: "Audits",
    findings: "Findings",
    cars: "CAR / CAPA",
    risk: "Risk & Opportunities",
    "change-control": "Change Control",
    system: "System & Processes",
    documents: "Controlled Documents",
    suppliers: "Suppliers",
    "equipment-calibration": "Equipment & Calibration",
    "external-interface": "External Interface",
    "management-review": "Management Review",
    reports: "Reports & Analytics",
    "evidence-vault": "Evidence Vault",
    settings: "QMS Settings",
    aerodoc: "AeroDoc",
  };
  return segment ? labels[segment] || segment.replaceAll("-", " ") : "Quality Control Centre";
}

function pathMatches(current: string, target: string): boolean {
  const cleanTarget = target.split("?")[0].replace(/\/$/, "");
  return current === cleanTarget || current.startsWith(`${cleanTarget}/`);
}

function tabIsActive(tab: ContextTab, pathname: string, search: string): boolean {
  const target = tab.path.split("?")[0].replace(/\/$/, "");
  const current = pathname.replace(/\/$/, "");
  if (tab.queryTab) {
    return pathMatches(current, target)
      && (new URLSearchParams(search).get("tab") || "war-room") === tab.queryTab;
  }
  if (tab.activePrefixes?.some((prefix) => pathMatches(current, prefix))) return true;
  if (tab.exact) return current === target;
  return pathMatches(current, target);
}

function topLevelTabs(basePath: string): ContextTab[] {
  return [
    { id: "overview", label: "Control Centre", path: basePath, icon: Gauge, exact: true },
    { id: "work", label: "My Work", path: `${basePath}/inbox/assigned-to-me`, icon: Inbox, activePrefixes: [`${basePath}/inbox`] },
    { id: "calendar", label: "Calendar", path: `${basePath}/calendar/month`, icon: CalendarDays, activePrefixes: [`${basePath}/calendar`] },
    { id: "audits", label: "Audits", path: `${basePath}/audits/dashboard`, icon: ClipboardCheck, activePrefixes: [`${basePath}/audits`] },
    { id: "findings", label: "Findings", path: `${basePath}/findings/register`, icon: ShieldCheck, activePrefixes: [`${basePath}/findings`] },
    { id: "cars", label: "CAR / CAPA", path: `${basePath}/cars/register`, icon: ListChecks, activePrefixes: [`${basePath}/cars`] },
    { id: "reports", label: "Reports", path: `${basePath}/reports/executive-dashboard`, activePrefixes: [`${basePath}/reports`] },
  ];
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
        : topLevelTabs(route.basePath);

  const title = isAuditRecord
    ? `Audit ${safeRecordKey}`
    : isCarRecord
      ? `CAR ${safeRecordKey}`
      : moduleTitle(moduleSegment);

  const primaryAction = isAuditRecord
    ? { label: "Audit register", path: `${route.basePath}/audits/register`, icon: ClipboardCheck }
    : isCarRecord
      ? { label: "CAR register", path: `${route.basePath}/cars/register`, icon: ListChecks }
      : moduleSegment === "findings"
        ? { label: "New finding", path: `${route.basePath}/findings/new`, icon: Plus }
        : moduleSegment === "cars"
          ? { label: "Create CAR", path: `${route.basePath}/cars/new`, icon: Plus }
          : { label: "Schedule audit", path: `${route.basePath}/audits/plan?view=calendar&create=1`, icon: Plus };

  const PrimaryIcon = primaryAction.icon;

  return createPortal(
    <section className="quality-context-bar" aria-label="Quality workspace navigation">
      <div className="quality-context-bar__identity">
        <span className="quality-context-bar__mark"><ShieldCheck size={17} aria-hidden="true" /></span>
        <span><small>Quality workspace</small><strong>{title}</strong></span>
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
        <span className="quality-context-bar__live" title="QMS pages refresh automatically while active"><RefreshCw size={13} aria-hidden="true" /> Live</span>
        <button type="button" className="quality-context-bar__primary" onClick={() => navigate(primaryAction.path)}><PrimaryIcon size={15} aria-hidden="true" /><span>{primaryAction.label}</span></button>
        <details className="quality-context-bar__more">
          <summary aria-label="More Quality pages"><MoreHorizontal size={17} /><ChevronDown size={13} /></summary>
          <div>
            <button type="button" onClick={() => navigate(`${route.basePath}/risk/register`)}>Risk & opportunities</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/change-control/register`)}>Change control</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/documents/library`)}>Controlled documents</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/management-review/dashboard`)}>Management review</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/evidence-vault/search`)}>Evidence vault</button>
            <button type="button" onClick={() => navigate(`${route.basePath}/settings/general`)}>QMS settings</button>
          </div>
        </details>
      </div>
    </section>,
    mountTarget,
  );
};

export default QualityContextTabs;
