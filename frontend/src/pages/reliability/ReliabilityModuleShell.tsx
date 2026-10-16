/* eslint-disable react-refresh/only-export-components */
import React, { useState } from "react";
import {
  Activity, AlertCircle, BarChart3, BookOpenCheck, CalendarClock, ChartNoAxesCombined,
  ChevronDown, ChevronRight, CircleGauge, ClipboardCheck, ClipboardList,
  CloudDownload, Database, FileBarChart2, FileCheck2, FileSpreadsheet,
  FileText, Gauge, GitBranch, History, Layers3, ListChecks, Network,
  PanelLeftClose, PanelLeftOpen, SearchCheck, Settings2, ShieldCheck,
  SlidersHorizontal, TrendingUp, Wrench, type LucideIcon,
} from "lucide-react";
import { Link, NavLink, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import "./ReliabilityModuleShell.css";

export type ReliabilityArea = { label: string; path: string; description?: string };
export const RELIABILITY_GROUPS: Array<{ label: string; items: ReliabilityArea[] }> = [
  { label: "Command & analysis", items: [
    { label: "Overview", path: "", description: "Exceptions and priorities" },
    { label: "Fleet trends", path: "analytics/operational", description: "Measured rates, ATA and aircraft comparisons" },
    { label: "Network delays", path: "analytics/network", description: "Station and route delay burden" },
    { label: "Component reliability", path: "analytics/components", description: "Removals, NFF and shop returns" },
    { label: "Engine health", path: "analytics/engineering", description: "EHM parameters and engine status" },
    { label: "Oil consumption graphs", path: "analytics/oil", description: "Engine uplift and OCR trends" },
    { label: "Deferral controls", path: "analytics/deferrals", description: "MEL/CDL expiry and recurrence" },
    { label: "FRACAS analysis", path: "analytics/fracas", description: "Cases, actions and effectiveness" },
    { label: "Source confidence", path: "analytics/data", description: "Freshness and data-quality exceptions" },
    { label: "Analytical evidence", path: "analytics/evidence", description: "Drill-down and ranked registers" },
  ] },
  { label: "Operations & investigations", items: [
    { label: "Source control", path: "operations", description: "Flight, deferral, shop, SMS and QMS" },
    { label: "Occurrences", path: "events" },
    { label: "Technical alerts", path: "alerts" },
    { label: "FRACAS cases", path: "cases" },
    { label: "Engine status", path: "engines" },
    { label: "Oil consumption", path: "octm" },
  ] },
  { label: "Programme data", items: [
    { label: "Data registers", path: "workbook-registers" },
    { label: "Source field mapping", path: "workbook-mapping" },
    { label: "Workbook intake", path: "workbook-imports" },
    { label: "CSV staging", path: "workbook-csv" },
    { label: "Statistical alerts", path: "statistical-alerts" },
    { label: "Data quality", path: "data-quality" },
    { label: "Source connectors", path: "sources" },
    { label: "Import monitoring", path: "ingestion" },
  ] },
  { label: "Governance & reporting", items: [
    { label: "Formula library", path: "analytics/formulae" },
    { label: "Metric administration", path: "analytics/administration" },
    { label: "Approval & effectivity", path: "analytics/governance" },
    { label: "Calculation evidence", path: "analytics/calculations" },
    { label: "Controlled reporting", path: "formal-review" },
    { label: "Reporting obligations", path: "formal-reports" },
    { label: "AMP recommendations", path: "programme-reports" },
    { label: "Report distribution", path: "report-distribution" },
    { label: "Report layouts", path: "workbook-reports" },
    { label: "Management reports", path: "management-reports" },
  ] },
];

const RELIABILITY_ICONS: Record<string, LucideIcon> = {
  "": Gauge, "analytics/operational": TrendingUp, "analytics/network": Network,
  "analytics/components": Wrench, "analytics/engineering": Activity,
  "analytics/oil": ChartNoAxesCombined, "analytics/deferrals": CalendarClock,
  "analytics/fracas": GitBranch, "analytics/data": SearchCheck,
  "analytics/evidence": Database, "operations": CircleGauge,
  "events": ClipboardList, "alerts": AlertCircle, "cases": GitBranch,
  "engines": Activity, "octm": ChartNoAxesCombined,
  "workbook-registers": FileSpreadsheet, "workbook-mapping": Settings2,
  "workbook-imports": CloudDownload, "workbook-csv": FileSpreadsheet,
  "statistical-alerts": BarChart3, "data-quality": ShieldCheck,
  "sources": Network, "ingestion": History,
  "analytics/formulae": BookOpenCheck, "analytics/administration": SlidersHorizontal,
  "analytics/governance": ClipboardCheck, "analytics/calculations": Layers3,
  "formal-review": FileCheck2, "formal-reports": CalendarClock,
  "programme-reports": ListChecks, "report-distribution": FileBarChart2,
  "workbook-reports": FileText, "management-reports": FileBarChart2,
};
function activeLocation(pathname: string): string {
  const portion = pathname.split("/reliability/")[1];
  if (portion === undefined || portion === "" || portion === "workbench") return "";
  // A canonical register detail remains in its owning register.
  if (portion.startsWith("events/")) return "events";
  if (portion.startsWith("alerts/")) return "alerts";
  if (portion.startsWith("cases/")) return "cases";
  return portion.replace(/\/$/, "");
}

export function ReliabilityModuleShell({ children }: { children: React.ReactNode }): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const { pathname, search } = useLocation();
  const base = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const active = activeLocation(pathname);
  const [compact, setCompact] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<string[]>([]);
  const toggleGroup = (name: string) => setCollapsedGroups((current) =>
    current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const selected = RELIABILITY_GROUPS.flatMap((group) => group.items).find((item) => item.path === active);
  return <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
    <div className={`rel-shell ${compact ? "rel-shell--focus" : ""}`}>
      <aside className="rel-shell__rail" aria-label="Reliability module workspaces">
        <div className="rel-shell__rail-top">
          <Link to={base} className="rel-shell__brand"><ChartNoAxesCombined size={22} aria-hidden="true" />
            <span>Reliability <small>Intelligence workspace</small></span></Link>
          <button type="button" className="rel-shell__focus" onClick={() => setCompact((value) => !value)}
            aria-expanded={!compact} aria-controls="rel-shell-navigation">
            {compact ? <><PanelLeftOpen size={17} aria-hidden="true" /> Show navigation</> : <><PanelLeftClose size={17} aria-hidden="true" /> Focus view</>}
          </button>
        </div>
        <nav id="rel-shell-navigation" className="rel-shell__navigation" aria-label="Reliability navigation">
          {RELIABILITY_GROUPS.map((group) => {
            const collapsed = collapsedGroups.includes(group.label);
            const hasActive = group.items.some((item) => item.path === active);
            const id = "reliability-group-" + group.label.replace(/[^a-zA-Z]/g, "");
            return <section className="rel-shell__group" key={group.label}>
              <h2><button type="button" onClick={() => toggleGroup(group.label)}
                aria-expanded={!collapsed || hasActive} aria-controls={id}>
                {group.label}{collapsed && !hasActive ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
              </button></h2>
              <div id={id} hidden={collapsed && !hasActive}>
                {group.items.map((item) => {
                  const Icon = RELIABILITY_ICONS[item.path] || Layers3;
                  return <NavLink key={item.path}
                    to={(item.path ? base + "/" + item.path : base) + (pathname.includes("/reliability/analytics/") && item.path.startsWith("analytics/") ? search : "")}
                    end={item.path === ""}
                    className={({ isActive }) => `rel-shell__link ${isActive || active === item.path ? "is-active" : ""}`}
                    title={item.description || item.label}>
                    <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>;
                })}
              </div>
            </section>;
          })}
        </nav>
      </aside>
      <div className="rel-shell__body">
        <div className="rel-shell__context" aria-label="Current Reliability workspace">
          <span>Reliability</span><span aria-hidden="true">/</span>
          <strong>{selected?.label || "Operational detail"}</strong>
          <span className="rel-shell__context-hint"><ShieldCheck size={14} aria-hidden="true" /> Governed source evidence</span>
        </div>
        <div className="rel-shell__canvas">{children}</div>
      </div>
    </div>
  </DepartmentLayout>;
}
