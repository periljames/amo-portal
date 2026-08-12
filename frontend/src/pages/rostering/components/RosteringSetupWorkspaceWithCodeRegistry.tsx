import { ControlledRosterSettingsPanel } from "./ControlledRosterSettingsPanel";
import { RosterCodeRegistryPanel } from "./RosterCodeRegistryPanel";
import { RosteringSetupWorkspace } from "./RosteringSetupWorkspace";

export function RosteringSetupWorkspaceWithCodeRegistry() {
  return (
    <div className="rs-setup__stack">
      <RosterCodeRegistryPanel />
      <ControlledRosterSettingsPanel />
      <RosteringSetupWorkspace />
    </div>
  );
}
