import React, { useState } from "react";
import { getMaintenanceSettings, saveMaintenanceSettings } from "../../services/maintenance";
import { MaintenancePageShell, maintenanceActionAllowed } from "./components";

const MaintenanceSettingsPage: React.FC = () => {
  const [settings, setSettings] = useState(getMaintenanceSettings());
  const canEdit = maintenanceActionAllowed("maintenance.manage-settings");

  return (
    <MaintenancePageShell title="Maintenance Settings" requiredFeature="maintenance.settings">
      <div className="card" style={{ display: "grid", gap: 8, maxWidth: 700 }}>
        <label>Default WO numbering prefix<input className="input" value={settings.woPrefix} onChange={(e) => setSettings({ ...settings, woPrefix: e.target.value })} disabled={!canEdit} /></label>
        <label><input type="checkbox" checked={settings.nrApprovalRequired} onChange={(e) => setSettings({ ...settings, nrApprovalRequired: e.target.checked })} disabled={!canEdit} /> NR approval required</label>
        <label><input type="checkbox" checked={settings.inspectionsEnabled} onChange={(e) => setSettings({ ...settings, inspectionsEnabled: e.target.checked })} disabled={!canEdit} /> Inspections/holds enabled</label>
        <label><input type="checkbox" checked={settings.evidenceRequiredToCloseTask} onChange={(e) => setSettings({ ...settings, evidenceRequiredToCloseTask: e.target.checked })} disabled={!canEdit} /> Evidence required to close tasks</label>
        <button className="btn btn-primary" disabled={!canEdit} onClick={() => { saveMaintenanceSettings(settings); alert("Settings saved"); }}>Save tenant defaults</button>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceSettingsPage;
