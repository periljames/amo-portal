import React from "react";
import { NavLink, useParams } from "react-router-dom";
import "./ReliabilityWorkspaceNavigation.css";

const groups = [
  { name: "Monitor", items: [
    ["", "Overview"], ["analytics-trends", "Fleet trends"], ["analytics-engines", "Engine health"],
    ["analytics-evidence", "Evidence tables"], ["octm", "Oil consumption"],
  ] },
  { name: "Investigate", items: [
    ["events", "Occurrences"], ["alerts", "Alerts"], ["cases", "FRACAS"], ["fleet", "Fleet analysis"],
    ["systems", "Systems"], ["components", "Components"],
  ] },
  { name: "Source data", items: [
    ["operations", "Operational feeds"], ["workbook-registers", "Data registers"],
    ["workbook-mapping", "Imports & mapping"], ["data-quality", "Data quality"],
  ] },
  { name: "Govern", items: [
    ["analytics-formulae", "Metrics & formulae"], ["analytics-calculations", "Calculations"],
    ["statistical-alerts", "Statistical alerts"], ["formal-review", "Formal review"],
    ["formal-reports", "Formal reporting"], ["programme-reports", "Programme changes"],
  ] },
] as const;

export default function ReliabilityWorkspaceNavigation(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const base = "/maintenance/" + encodeURIComponent(amoCode) + "/reliability";
  return <nav className="rel-workspace-nav" aria-label="Reliability module workspaces">
    {groups.map((group) => <div className="rel-workspace-nav__group" key={group.name}>
      <span className="rel-workspace-nav__label">{group.name}</span>
      <div className="rel-workspace-nav__links">
        {group.items.map(([route, label]) => <NavLink key={route || "overview"}
          end={route === ""} to={route ? base + "/" + route : base}
          className={({ isActive }) => isActive ? "rel-workspace-nav__link active" : "rel-workspace-nav__link"}>
          {label}
        </NavLink>)}
      </div>
    </div>)}
  </nav>;
}
