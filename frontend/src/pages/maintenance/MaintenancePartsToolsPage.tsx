import React, { useState } from "react";
import { listPartToolRequests, savePartToolRequest, type PartToolStatus } from "../../services/maintenance";
import { MaintenancePageShell, maintenanceActionAllowed } from "./components";

const MaintenancePartsToolsPage: React.FC = () => {
  const [rows, setRows] = useState(listPartToolRequests());
  const [form, setForm] = useState({ woId: "", itemType: "Part", description: "", qty: "1", requestedBy: "" });
  const canEdit = maintenanceActionAllowed("maintenance.request-parts");

  const add = () => {
    if (!canEdit) return;
    const ok = savePartToolRequest({ id: crypto.randomUUID(), woId: Number(form.woId), itemType: form.itemType as any, description: form.description, qty: Number(form.qty), status: "REQUESTED", requestedBy: form.requestedBy, requestedAt: new Date().toISOString(), updatedAt: new Date().toISOString() });
    if (!ok) {
      alert("Go Live is active. Demo/local parts-tools editing is disabled.");
      return;
    }
    setRows(listPartToolRequests());
  };

  const update = (id: string, status: PartToolStatus) => {
    if (!canEdit) return;
    const row = rows.find((item) => item.id === id);
    if (!row) return;
    const ok = savePartToolRequest({ ...row, status, updatedAt: new Date().toISOString() });
    if (!ok) {
      alert("Go Live is active. Demo/local parts-tools editing is disabled.");
      return;
    }
    setRows(listPartToolRequests());
  };

  return (
    <MaintenancePageShell title="Parts & Tools Requests" requiredFeature="maintenance.parts-tools">
      <div className="card" style={{ display: "grid", gap: 8, marginBottom: 12 }}>
        <h3>New request</h3>
        <input className="input" placeholder="WO ID" value={form.woId} onChange={(e) => setForm({ ...form, woId: e.target.value })} disabled={!canEdit} />
        <select className="input" value={form.itemType} onChange={(e) => setForm({ ...form, itemType: e.target.value })} disabled={!canEdit}><option>Part</option><option>Tool</option><option>GSE</option></select>
        <input className="input" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} disabled={!canEdit} />
        <input className="input" placeholder="Qty" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} disabled={!canEdit} />
        <input className="input" placeholder="Requested by" value={form.requestedBy} onChange={(e) => setForm({ ...form, requestedBy: e.target.value })} disabled={!canEdit} />
        <button className="btn btn-primary" onClick={add} disabled={!canEdit}>Create request</button>
      </div>
      <div className="card">
        <table className="table">
          <thead><tr><th>WO</th><th>Type</th><th>Description</th><th>Qty</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.id}><td>{row.woId}</td><td>{row.itemType}</td><td>{row.description}</td><td>{row.qty}</td><td>{row.status}</td><td><button className="btn btn-secondary" onClick={() => update(row.id, "ISSUED")} disabled={!canEdit}>Issue</button></td></tr>)}</tbody>
        </table>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenancePartsToolsPage;
