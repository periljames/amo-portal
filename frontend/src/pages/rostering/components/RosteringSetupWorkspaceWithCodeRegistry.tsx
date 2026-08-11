import { RosterCodeRegistryPanel } from "./RosterCodeRegistryPanel";
import { RosteringSetupWorkspace } from "./RosteringSetupWorkspace";

export function RosteringSetupWorkspaceWithCodeRegistry() {
  return (
    <div className="rs-setup__stack">
      <RosterCodeRegistryPanel />
      <RosteringSetupWorkspace />
    </div>
  );
}
