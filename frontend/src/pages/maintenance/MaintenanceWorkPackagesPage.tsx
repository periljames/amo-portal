import React, { useEffect, useMemo, useState } from "react";
import { listWorkOrders, listTasksForWorkOrder, type WorkOrderRead } from "../../services/workOrders";
import { listInspections } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceWorkPackagesPage: React.FC = () => {
  const [wos, setWos] = useState<WorkOrderRead[]>([]);
  const [progress, setProgress] = useState<Record<number, number>>({});
  useEffect(()=>{ listWorkOrders({ limit: 500 }).then(async (rows)=>{ setWos(rows); const map: Record<number, number> = {}; for (const w of rows){ const tasks = await listTasksForWorkOrder(w.id).catch(()=>[]); map[w.id] = tasks.length ? Math.round((tasks.filter((t)=>t.status==="COMPLETED"||t.status==="INSPECTED").length / tasks.length)*100):0; } setProgress(map); }).catch(()=>setWos([]));},[]);
  const holds = listInspections().filter((x)=>x.holdFlag && x.status!=="DONE");
  const grouped = useMemo(()=>wos.reduce<Record<string,WorkOrderRead[]>>((a,w)=>{ const k=w.work_package_ref||"UNASSIGNED"; (a[k] ||= []).push(w); return a; },{}),[wos]);
  return <MaintenancePageShell title="Work Package Execution">
    {Object.entries(grouped).map(([wp, rows])=><div className="card" key={wp} style={{marginBottom:12}}><h3>{wp}</h3><table className="table"><thead><tr><th>WO</th><th>Tail</th><th>Progress</th><th>Holds</th></tr></thead><tbody>{rows.map((w)=><tr key={w.id}><td>{w.wo_number}</td><td>{w.aircraft_serial_number}</td><td>{progress[w.id] || 0}%</td><td>{holds.filter((h)=>h.woId===w.id).length}</td></tr>)}</tbody></table></div>)}
  </MaintenancePageShell>;
};

export default MaintenanceWorkPackagesPage;
