import { RosterCommitmentBoard } from "./RosterCommitmentBoard";
import { RosterPlannerV2 } from "./RosterPlannerV2";

export function UnifiedRosterPlanner() {
  return (
    <div className="wr-unified-planner">
      <RosterCommitmentBoard />
      <RosterPlannerV2 />
    </div>
  );
}
