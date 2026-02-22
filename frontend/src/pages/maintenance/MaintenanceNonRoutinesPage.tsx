import React, { useState } from "react";
import { Link } from "react-router-dom";
import { listNonRoutines, saveNonRoutine, type NonRoutineItem } from "../../services/maintenance";
import { MaintenancePageShell, StatusPill } from "./components";

const MaintenanceNonRoutinesPage: React.FC = () => {
  const [rows, setRows] = useState<NonRoutineItem[]>(listNonRoutines());
  const [form, setForm] = useState({ tail: "", woId: "", taskId: "", description: "", dispositionRequired: true });
  const submit = () => {
    const item: NonRoutineItem = { id: crypto.randomUUID(), tail: form.tail, woId: Number(form.woId), taskId: form.taskId ? Number(form.taskId) : undefined, description: form.description, dispositionRequired: form.dispositionRequired, status: "DRAFT", evidence: [], createdAt: new Date().toISOString() };
    const ok = saveNonRoutine(item);
    if (!ok) { alert("Go Live is active. Demo/local NR editing is disabled."); return; }
    setRows(listNonRoutines());
  };
  return <MaintenancePageShell title="Non-Routines">
    <div className="card" style={{ display:"grid", gap:8, marginBottom: 12 }}>
      <h3>Create NR</h3>
      <input className="input" placeholder="Tail" value={form.tail} onChange={(e)=>setForm({...form, tail:e.target.value})}/>
      <input className="input" placeholder="WO ID" value={form.woId} onChange={(e)=>setForm({...form, woId:e.target.value})}/>
      <input className="input" placeholder="Task ID (optional)" value={form.taskId} onChange={(e)=>setForm({...form, taskId:e.target.value})}/>
      <textarea className="input" placeholder="Description" value={form.description} onChange={(e)=>setForm({...form, description:e.target.value})}/>
      <label><input type="checkbox" checked={form.dispositionRequired} onChange={(e)=>setForm({...form, dispositionRequired:e.target.checked})}/> Disposition required</label>
      <button className="btn btn-primary" onClick={submit}>Create NR</button>
    </div>
    <div className="card"><table className="table"><thead><tr><th>ID</th><th>Tail</th><th>WO</th><th>Status</th><th>Workflow</th></tr></thead><tbody>{rows.map((r)=><tr key={r.id}><td><Link to={`/maintenance/non-routines/${r.id}`}>{r.id.slice(0,8)}</Link></td><td>{r.tail}</td><td>{r.woId}</td><td><StatusPill label={r.status} /></td><td>Draft → Submitted → Approved/Rejected → Executed → Closed</td></tr>)}</tbody></table></div>
  </MaintenancePageShell>;
};

export default MaintenanceNonRoutinesPage;
