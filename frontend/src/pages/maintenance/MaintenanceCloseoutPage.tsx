import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listWorkOrders, listTasksForWorkOrder, type WorkOrderRead } from "../../services/workOrders";
import { getContext } from "../../services/auth";
import { getMaintenanceSettings, listInspections } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceCloseoutPage: React.FC = () => {
  const [rows, setRows] = useState<WorkOrderRead[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [checks, setChecks] = useState<{ tasksDone: boolean; holdsReleased: boolean; inspectionsDone: boolean; evidenceOk: boolean }>({ tasksDone: false, holdsReleased: false, inspectionsDone: false, evidenceOk: true });
  const navigate = useNavigate();
  const ctx = getContext();
  useEffect(()=>{ listWorkOrders({ limit: 500 }).then(setRows).catch(()=>setRows([])); },[]);
  const validate = async (woId: number) => {
    const tasks = await listTasksForWorkOrder(woId).catch(()=>[]);
    const holds = listInspections().filter((x)=>x.woId===woId && x.holdFlag);
    const inspections = listInspections().filter((x)=>x.woId===woId);
    const settings = getMaintenanceSettings();
    setChecks({
      tasksDone: tasks.length > 0 && tasks.every((t)=>t.status === "COMPLETED" || t.status === "INSPECTED"),
      holdsReleased: holds.every((h)=>h.status === "DONE"),
      inspectionsDone: inspections.every((i)=>i.status === "DONE"),
      evidenceOk: !settings.evidenceRequiredToCloseTask,
    });
  };
  return <MaintenancePageShell title="Closeout & CRS Pending">
    <div className="card" style={{ marginBottom: 12 }}>
      <select className="input" value={selected || ""} onChange={(e)=>{ const id = Number(e.target.value); setSelected(id); validate(id); }}>
        <option value="">Select WO</option>{rows.map((w)=><option key={w.id} value={w.id}>{w.wo_number} ({w.status})</option>)}
      </select>
      <ul><li>All required tasks completed: {checks.tasksDone ? "✅" : "❌"}</li><li>All holds released: {checks.holdsReleased ? "✅" : "❌"}</li><li>Required inspections completed: {checks.inspectionsDone ? "✅" : "❌"}</li><li>Evidence settings satisfied: {checks.evidenceOk ? "✅" : "❌"}</li></ul>
      <div style={{display:"flex", gap:8}}><button className="btn btn-primary" disabled={!selected || !(checks.tasksDone && checks.holdsReleased && checks.inspectionsDone && checks.evidenceOk)} onClick={()=>navigate(`/maintenance/${ctx.amoSlug || 'system'}/${(ctx.department || 'planning').toLowerCase()}/crs/new`)}>Issue CRS</button></div>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceCloseoutPage;
