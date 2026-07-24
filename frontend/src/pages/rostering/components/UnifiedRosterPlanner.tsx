import { RosterPlannerV2 } from "./RosterPlannerV2";

export function UnifiedRosterPlanner() {
  return (
    <div style={{ display: "grid", gap: "0.5rem", minWidth: 0 }}>
      <details className="wr-inline-disclosure">
        <summary>Commitment sources</summary>
        <p>
          Approved leave, assigned training and Quality work appear directly in the planner.
          Edit them in their source modules rather than creating duplicate roster records.
        </p>
      </details>
      <RosterPlannerV2 />
    </div>
  );
}
