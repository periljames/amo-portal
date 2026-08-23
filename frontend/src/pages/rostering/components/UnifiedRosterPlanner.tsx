import "./roster-planner-ux.css";
import "./roster-planner-actions.css";
import "./roster-generation.css";
import "./roster-spreadsheet-overrides.css";

import { useEffect, useRef } from "react";
import { Download, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { RosterComplianceControlCenter } from "./RosterComplianceControlCenter";
import { RosterPlannerV2 } from "./RosterPlannerV2";
import { RosterSpreadsheetInteractions } from "./RosterSpreadsheetInteractions";

export function UnifiedRosterPlanner() {
  const { amoCode = "" } = useParams();
  const reportsRoute = `/maintenance/${encodeURIComponent(amoCode)}/rostering/reports`;
  const governanceRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const container = governanceRef.current;
    if (!container) return;

    const surfaceHardBlock = () => {
      const blockerBadges = Array.from(container.querySelectorAll<HTMLElement>(".wr-pill--blocker"));
      const hasHardBlock = blockerBadges.some((badge) => {
        const text = (badge.textContent || "").trim().toUpperCase();
        return text.includes("HARD BLOCK") && !text.startsWith("0 ");
      });
      if (hasHardBlock) container.open = true;
    };

    surfaceHardBlock();
    const observer = new MutationObserver(surfaceHardBlock);
    observer.observe(container, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="wr-planner-workspace">
      <details ref={governanceRef} className="wr-planner-governance-shortcut">
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
      <RosterSpreadsheetInteractions />
    </div>
  );
}
