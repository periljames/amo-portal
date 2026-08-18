import "./roster-planner-ux.css";
import "./roster-planner-actions.css";
import "./roster-generation.css";

import { Download, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { RosterComplianceControlCenter } from "./RosterComplianceControlCenter";
import { RosterPlannerV2 } from "./RosterPlannerV2";

export function UnifiedRosterPlanner() {
  const { amoCode = "" } = useParams();
  const reportsRoute = `/maintenance/${encodeURIComponent(amoCode)}/rostering/reports`;

  return (
    <div className="wr-planner-workspace">
      <details className="wr-planner-governance-shortcut">
        <summary aria-label="Open compliance checks" title="Compliance checks">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>Checks</span>
        </summary>
        <aside className="wr-planner-governance-drawer" aria-label="Roster compliance and governed exceptions">
          <RosterComplianceControlCenter />
        </aside>
      </details>
      <Link
        className="wr-planner-download-shortcut"
        to={reportsRoute}
        aria-label="Download or export roster"
        title="Download / export"
      >
        <Download size={17} aria-hidden="true" />
      </Link>
      <RosterPlannerV2 />
    </div>
  );
}
