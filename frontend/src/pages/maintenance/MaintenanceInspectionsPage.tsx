import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { listInspections, saveInspection, type InspectionItem } from "../../services/maintenance";
import { MaintenancePageShell, buildMaintenancePath, maintenanceActionAllowed } from "./components";

const MaintenanceInspectionsPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const [rows, setRows] = useState<InspectionItem[]>(listInspections());
  const [form, setForm] = useState({ woId: "", tail: "", inspectionType: "", requiredByRole: "QUALITY", holdFlag: true });
  const canEdit = maintenanceActionAllowed("maintenance.perform-inspection");

  const add = () => {
    if (!canEdit) return;
    const ok = saveInspection({
      id: crypto.randomUUID(),
      woId: Number(form.woId),
      tail: form.tail,
      inspectionType: form.inspectionType,
      requiredByRole: form.requiredByRole,
      status: "REQUESTED",
      findings: "",
      evidence: [],
      holdFlag: form.holdFlag,
    });
    if (!ok) {
      alert("Go Live is active. Demo/local inspection editing is disabled.");
      return;
    }
    setRows(listInspections());
  };

  return (
    <MaintenancePageShell title="Inspections & Holds" requiredFeature="maintenance.inspections">
      <div className="card" style={{ display: "grid", gap: 8, marginBottom: 12 }}>
        <h3>Create inspection</h3>
        <input className="input" placeholder="WO ID" value={form.woId} onChange={(e) => setForm({ ...form, woId: e.target.value })} disabled={!canEdit} />
        <input className="input" placeholder="Tail" value={form.tail} onChange={(e) => setForm({ ...form, tail: e.target.value })} disabled={!canEdit} />
        <input className="input" placeholder="Inspection type" value={form.inspectionType} onChange={(e) => setForm({ ...form, inspectionType: e.target.value })} disabled={!canEdit} />
        <input className="input" placeholder="Required role" value={form.requiredByRole} onChange={(e) => setForm({ ...form, requiredByRole: e.target.value })} disabled={!canEdit} />
        <label><input type="checkbox" checked={form.holdFlag} onChange={(e) => setForm({ ...form, holdFlag: e.target.checked })} disabled={!canEdit} /> Apply hold flag</label>
        <button className="btn btn-primary" onClick={add} disabled={!canEdit}>Create inspection</button>
      </div>
      <div className="card">
        <table className="table">
          <thead><tr><th>ID</th><th>WO</th><th>Tail</th><th>Type</th><th>Status</th><th>Hold</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td><Link to={buildMaintenancePath(`inspections/${row.id}`, { amoCode })}>{row.id.slice(0, 8)}</Link></td>
                <td>{row.woId}</td>
                <td>{row.tail}</td>
                <td>{row.inspectionType}</td>
                <td>{row.status}</td>
                <td>{row.holdFlag ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceInspectionsPage;
