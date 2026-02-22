import React, { useState } from "react";
import { listPartToolRequests, savePartToolRequest, type PartToolStatus } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenancePartsToolsPage: React.FC = () => {
  const [rows, setRows] = useState(listPartToolRequests());
  const [form, setForm] = useState({ woId: "", itemType: "Part", description: "", qty: "1", requestedBy: "" });
  const add = () => {
    savePartToolRequest({ id: crypto.randomUUID(), woId: Number(form.woId), itemType: form.itemType as any, description: form.description, qty: Number(form.qty), status: "REQUESTED", requestedBy: form.requestedBy, requestedAt: new Date().toISOString(), updatedAt: new Date().toISOString() });
    setRows(listPartToolRequests());
  };
  const update = (id: string, status: PartToolStatus) => { const row = rows.find((r)=>r.id===id); if (!row) return; savePartToolRequest({ ...row, status, updatedAt: new Date().toISOString()}); setRows(listPartToolRequests()); };
  return <MaintenancePageShell title="Parts & Tools Requests">
    <div className="card" style={{display:"grid", gap:8, marginBottom:12}}>
      <h3>New request</h3>
      <input className="input" placeholder="WO ID" value={form.woId} onChange={(e)=>setForm({...form, woId:e.target.value})}/>
      <select className="input" value={form.itemType} onChange={(e)=>setForm({...form, itemType:e.target.value})}><option>Part</option><option>Tool</option><option>GSE</option></select>
      <input className="input" placeholder="Description" value={form.description} onChange={(e)=>setForm({...form, description:e.target.value})}/>
      <input className="input" placeholder="Qty" value={form.qty} onChange={(e)=>setForm({...form, qty:e.target.value})}/>
      <input className="input" placeholder="Requested by" value={form.requestedBy} onChange={(e)=>setForm({...form, requestedBy:e.target.value})}/>
      <button className="btn btn-primary" onClick={add}>Create request</button>
    </div>
    <div className="card"><table className="table"><thead><tr><th>WO</th><th>Type</th><th>Description</th><th>Qty</th><th>Status</th><th>Actions</th></tr></thead><tbody>{rows.map((r)=><tr key={r.id}><td>{r.woId}</td><td>{r.itemType}</td><td>{r.description}</td><td>{r.qty}</td><td>{r.status}</td><td><button className="btn btn-secondary" onClick={()=>update(r.id,"ISSUED")}>Issue</button></td></tr>)}</tbody></table></div>
  </MaintenancePageShell>;
};

export default MaintenancePartsToolsPage;
