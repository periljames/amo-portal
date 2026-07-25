import "./roster-setup-refinement.css";

import { RosterPeriodQuickActions } from "./RosterPeriodQuickActions";
import { RosterRuleQuickEditor } from "./RosterRuleQuickEditor";
import { UnifiedRosterSettings } from "./UnifiedRosterSettings";

export function RosterSetupWorkspace() {
  return (
    <div className="wr-setup-workspace">
      <RosterPeriodQuickActions />
      <RosterRuleQuickEditor />
      <UnifiedRosterSettings />
    </div>
  );
}
