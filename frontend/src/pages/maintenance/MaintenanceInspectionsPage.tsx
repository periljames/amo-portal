import React, { useState } from "react";
import { Link } from "react-router-dom";
import { listInspections, saveInspection , type InspectionItem } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceInspectionsPage: React.FC = () => {
  const [rows, setRows] = useState<InspectionItem[]>(listInspections());
  const [form, setForm] = useState({ woId: "", tail: "", inspectionType: "", requiredByRole: "QUALITY", holdFlag: true });
  const add = () => { saveInspection({ id: crypto.randomUUID(), woId: Number(form.woId), tail: form.tail, inspectionType: form.inspectionType, requiredByRole: form.requiredByRole, status: "REQUESTED", findings: "", evidence: [], holdFlag: form.holdFlag }); setRows(listInspections()); };
  return <MaintenancePageShell title="Inspections & Holds">
    <div className="card" style={{display:"grid", gap:8, marginBottom:12}}>
      <h3>Create inspection</h3>
      <input className="input" placeholder="WO ID" value={form.woId} onChange={(e)=>setForm({...form, woId:e.target.value})}/>
      <input className="input" placeholder="Tail" value={form.tail} onChange={(e)=>setForm({...form, tail:e.target.value})}/>
      <input className="input" placeholder="Inspection type" value={form.inspectionType} onChange={(e)=>setForm({...form, inspectionType:e.target.value})}/>
      <input className="input" placeholder="Required role" value={form.requiredByRole} onChange={(e)=>setForm({...form, requiredByRole:e.target.value})}/>
      <label><input type="checkbox" checked={form.holdFlag} onChange={(e)=>setForm({...form, holdFlag:e.target.checked})}/> Apply hold flag</label>
      <button className="btn btn-primary" onClick={add}>Create inspection</button>
    </div>
    <div className="card"><table className="table"><thead><tr><th>ID</th><th>WO</th><th>Tail</th><th>Type</th><th>Status</th><th>Hold</th></tr></thead><tbody>{rows.map((r)=><tr key={r.id}><td><Link to={`/maintenance/inspections/${r.id}`}>{r.id.slice(0,8)}</Link></td><td>{r.woId}</td><td>{r.tail}</td><td>{r.inspectionType}</td><td>{r.status}</td><td>{r.holdFlag?"Yes":"No"}</td></tr>)}</tbody></table></div>
  </MaintenancePageShell>;
};

export default MaintenanceInspectionsPage;
