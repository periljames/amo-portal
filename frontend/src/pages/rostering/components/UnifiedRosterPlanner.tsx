import { RosterPlannerV2 } from "./RosterPlannerV2";

export function UnifiedRosterPlanner() {
  return <>
    <details className="wr-native-guidance">
      <summary>Commitment sources</summary>
      <p>Leave, training, Quality activity, and other protected commitments stay owned by their source modules rather than creating duplicate roster records.</p>
    </details>
    <RosterPlannerV2 />
  </>;
}
