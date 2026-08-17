import { GroupRotationPlanner } from "./GroupRotationPlanner";
import { RosterPlannerV2 } from "./RosterPlannerV2";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";

export function UnifiedRosterPlanner() {
  const permissionsQuery = useWorkforcePermissions();
  const permissions = permissionsQuery.data?.permissions || [];
  const canManagePatterns = permissions.includes("roster.manage_patterns") || permissions.includes("workforce.assign_patterns");

  return <>
    <details className="wr-native-guidance">
      <summary>Commitment sources</summary>
      <p>Leave, training, Quality activity, and other protected commitments stay owned by their source modules rather than creating duplicate roster records.</p>
    </details>
    {canManagePatterns ? <GroupRotationPlanner canManagePatterns={canManagePatterns} /> : null}
    <RosterPlannerV2 />
  </>;
}