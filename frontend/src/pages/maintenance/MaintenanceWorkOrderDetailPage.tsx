import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getWorkOrder, listTasksForWorkOrder, type TaskCardRead, type WorkOrderRead } from "../../services/workOrders";
import { getContext } from "../../services/auth";
import { listAllDefects, listInspections, listPartToolRequests } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const tabs = ["Overview","Tasks","Findings/NR","Parts/Tools","Inspections","Evidence","Activity","Audit Log"] as const;

const MaintenanceWorkOrderDetailPage: React.FC = () => {
  const { woId } = useParams<{ woId: string }>();
  const id = Number(woId);
  const [wo, setWo] = useState<WorkOrderRead | null>(null);
  const [tasks, setTasks] = useState<TaskCardRead[]>([]);
  const [active, setActive] = useState<typeof tabs[number]>("Overview");
  const navigate = useNavigate();
  const ctx = getContext();
  useEffect(() => { if (!id) return; getWorkOrder(id).then(setWo).catch(()=>setWo(null)); listTasksForWorkOrder(id).then(setTasks).catch(()=>setTasks([])); }, [id]);
  const defects = useMemo(() => [], []);
  const parts = listPartToolRequests().filter((p)=>p.woId===id);
  const inspections = listInspections().filter((i)=>i.woId===id);
  useEffect(()=>{ listAllDefects().then(()=>{}).catch(()=>{});},[]);
  return <MaintenancePageShell title={`WO ${wo?.wo_number || id}`}>
    <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom: 12 }}>{tabs.map((t)=><button key={t} className={`btn ${active===t?"btn-primary":"btn-secondary"}`} onClick={()=>setActive(t)}>{t}</button>)}</div>
    <div className="card">
      {active === "Overview" && <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(200px,1fr))",gap:8}}>
        <div><b>WO number</b><div>{wo?.wo_number}</div></div><div><b>Tail</b><div>{wo?.aircraft_serial_number}</div></div><div><b>Planned window</b><div>{wo?.open_date} → {wo?.due_date}</div></div><div><b>Status</b><div>{wo?.status}</div></div><div><b>Linked WP</b><div>{wo?.work_package_ref || "-"}</div></div><div><b>Created</b><div>{wo?.created_at || "-"}</div></div>
      </div>}
      {active === "Tasks" && <table className="table"><thead><tr><th>Task title/ATA</th><th>Status</th><th>Assigned</th><th>Sign-off</th><th>Evidence</th></tr></thead><tbody>{tasks.map(t=><tr key={t.id} style={{cursor:"pointer"}} onClick={()=>navigate(`/maintenance/${ctx.amoSlug || 'system'}/${(ctx.department || 'planning').toLowerCase()}/tasks/${t.id}`)}><td>{t.title} / {t.ata_chapter || "-"}</td><td>{t.status}</td><td>-</td><td>{t.status === "INSPECTED" ? "Yes" : "No"}</td><td>0</td></tr>)}</tbody></table>}
      {active === "Findings/NR" && <div><p>Defects/NR linked to this WO.</p><div>Linked defects: {defects.length}</div><button className="btn btn-secondary" onClick={()=>navigate('/maintenance/non-routines')}>Create NR</button></div>}
      {active === "Parts/Tools" && <table className="table"><thead><tr><th>Type</th><th>Description</th><th>Qty</th><th>Status</th></tr></thead><tbody>{parts.map(p=><tr key={p.id}><td>{p.itemType}</td><td>{p.description}</td><td>{p.qty}</td><td>{p.status}</td></tr>)}</tbody></table>}
      {active === "Inspections" && <table className="table"><thead><tr><th>Type</th><th>Required role</th><th>Status</th><th>Hold</th></tr></thead><tbody>{inspections.map(i=><tr key={i.id}><td>{i.inspectionType}</td><td>{i.requiredByRole}</td><td>{i.status}</td><td>{i.holdFlag?"Yes":"No"}</td></tr>)}</tbody></table>}
      {active === "Evidence" && <div><input className="input" placeholder="Add evidence link" /><button className="btn btn-primary" style={{marginLeft:8}}>Attach</button></div>}
      {active === "Activity" && <div>Activity timeline ready for manual entries and API events.</div>}
      {active === "Audit Log" && <div>Audit log panel ready (backend audit events can be wired by object id).</div>}
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceWorkOrderDetailPage;
