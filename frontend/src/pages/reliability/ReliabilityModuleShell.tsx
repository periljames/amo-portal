import React, { useState } from "react";
import { Link, NavLink, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import "./ReliabilityModuleShell.css";

export type ReliabilityArea = { label: string; path: string; description?: string };
export const RELIABILITY_GROUPS: Array<{ label: string; items: ReliabilityArea[] }> = [
  { label: "Command & analysis", items: [
    { label: "Overview", path: "", description: "Exceptions and priorities" },
    { label: "Operational charts", path: "analytics/operational", description: "Events, delays and fleet comparisons" },
    { label: "Engineering trends", path: "analytics/engineering", description: "Engines, components and health" },
    { label: "Statistical controls", path: "analytics/control", description: "Control limits and triggers" },
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
    { label: "Source mapping & imports", path: "workbook-mapping" },
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
    { label: "Report programme", path: "formal-reports" },
    { label: "Management report layouts", path: "workbook-reports" },
  ] },
];

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
  const { pathname } = useLocation();
  const base = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const active = activeLocation(pathname);
  const [compact, setCompact] = useState(false);
  const selected = RELIABILITY_GROUPS.flatMap((group) => group.items).find((item) => item.path === active);
  return <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
    <div className={`rel-shell ${compact ? "rel-shell--focus" : ""}`}>
      <aside className="rel-shell__rail" aria-label="Reliability module workspaces">
        <div className="rel-shell__rail-top">
          <Link to={base} className="rel-shell__brand">Reliability <span>workspace</span></Link>
          <button type="button" className="rel-shell__focus" onClick={() => setCompact((value) => !value)}
            aria-expanded={!compact} aria-controls="rel-shell-navigation">
            {compact ? "Show navigation" : "Focus view"}
          </button>
        </div>
        <nav id="rel-shell-navigation" className="rel-shell__navigation" aria-label="Reliability navigation">
          {RELIABILITY_GROUPS.map((group) => <section className="rel-shell__group" key={group.label}>
            <h2>{group.label}</h2>
            {group.items.map((item) => <NavLink
              key={item.path} to={item.path ? `${base}/${item.path}` : base}
              end={item.path === ""}
              className={({ isActive }) => `rel-shell__link ${isActive || active === item.path ? "is-active" : ""}`}
              title={item.description || item.label}
            >{item.label}</NavLink>)}
          </section>)}
        </nav>
      </aside>
      <div className="rel-shell__body">
        <div className="rel-shell__context" aria-label="Current Reliability workspace">
          <span>Reliability</span><span aria-hidden="true">/</span>
          <strong>{selected?.label || "Operational detail"}</strong>
          <span className="rel-shell__context-hint">Data, analysis and governed evidence</span>
        </div>
        <div className="rel-shell__canvas">{children}</div>
      </div>
    </div>
  </DepartmentLayout>;
}
