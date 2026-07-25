import "./roster-setup-refinement.css";

import { RosterPeriodQuickActions } from "./RosterPeriodQuickActions";
import { UnifiedRosterSettings } from "./UnifiedRosterSettings";

export function RosterSetupWorkspace() {
  return (
    <div className="wr-setup-workspace">
      <RosterPeriodQuickActions />
      <UnifiedRosterSettings />
    </div>
  );
}
