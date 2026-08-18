import "./roster-planner-ux.css";

import { Download } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { RosterPlannerV2 } from "./RosterPlannerV2";

export function UnifiedRosterPlanner() {
  const { amoCode = "" } = useParams();
  const reportsRoute = `/maintenance/${encodeURIComponent(amoCode)}/rostering/reports`;

  return (
    <div className="wr-planner-workspace">
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
