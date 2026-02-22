import React, { useState } from "react";
import { getMaintenanceSettings, saveMaintenanceSettings } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceSettingsPage: React.FC = () => {
  const [settings, setSettings] = useState(getMaintenanceSettings());
  return <MaintenancePageShell title="Maintenance Settings">
    <div className="card" style={{display:"grid", gap:8, maxWidth: 700}}>
      <label>Default WO numbering prefix<input className="input" value={settings.woPrefix} onChange={(e)=>setSettings({...settings, woPrefix:e.target.value})}/></label>
      <label><input type="checkbox" checked={settings.nrApprovalRequired} onChange={(e)=>setSettings({...settings, nrApprovalRequired:e.target.checked})}/> NR approval required</label>
      <label><input type="checkbox" checked={settings.inspectionsEnabled} onChange={(e)=>setSettings({...settings, inspectionsEnabled:e.target.checked})}/> Inspections/holds enabled</label>
      <label><input type="checkbox" checked={settings.evidenceRequiredToCloseTask} onChange={(e)=>setSettings({...settings, evidenceRequiredToCloseTask:e.target.checked})}/> Evidence required to close tasks</label>
      <button className="btn btn-primary" onClick={()=>{ saveMaintenanceSettings(settings); alert("Settings saved"); }}>Save tenant defaults</button>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceSettingsPage;
