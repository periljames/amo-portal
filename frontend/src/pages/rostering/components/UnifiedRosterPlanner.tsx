import { RosterCommitmentBoard } from "./RosterCommitmentBoard";
import { RosterPlannerV2 } from "./RosterPlannerV2";

export function UnifiedRosterPlanner() {
  return (
    <div style={{ display: "grid", gap: "1rem", minWidth: 0 }}>
      <RosterCommitmentBoard />
      <RosterPlannerV2 />
    </div>
  );
}
