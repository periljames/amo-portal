import React from "react";
import { listWorkOrders } from "../../services/workOrders";
import { listAllDefects } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const download = (name: string, content: string) => {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
};

const MaintenanceReportsPage: React.FC = () => {
  const exportDaily = async () => { const w = await listWorkOrders({ limit: 500 }); download("daily-production.csv", `wo,status,tail\n${w.map((x)=>`${x.wo_number},${x.status},${x.aircraft_serial_number}`).join("\n")}`); };
  const exportAgeing = async () => { const w = await listWorkOrders({ limit: 500 }); download("wo-ageing.csv", `wo,open_date,age_days\n${w.map((x)=>`${x.wo_number},${x.open_date || ""},${x.open_date ? Math.floor((Date.now()-new Date(x.open_date).getTime())/86400000):""}`).join("\n")}`); };
  const exportRepeatDefects = async () => { const d = await listAllDefects(); const grouped: Record<string, number> = {}; d.forEach((x)=>{ const k=`${x.aircraft_serial_number}-${x.operator_event_id || x.description.slice(0,20)}`; grouped[k]=(grouped[k]||0)+1;}); download("defect-repeat-list.csv", `defect_ref,count\n${Object.entries(grouped).filter(([,c])=>c>1).map(([k,c])=>`${k},${c}`).join("\n")}`); };
  return <MaintenancePageShell title="Maintenance Reports">
    <div className="card" style={{display:"grid", gap:8}}>
      <button className="btn btn-primary" onClick={exportDaily}>Export Daily production report (CSV)</button>
      <button className="btn btn-primary" onClick={exportAgeing}>Export WO status ageing report (CSV)</button>
      <button className="btn btn-primary" onClick={exportRepeatDefects}>Export Defect repeat list (CSV)</button>
      <button className="btn btn-secondary" onClick={()=>alert("PDF export wiring can reuse existing backend exports module.")}>Export Closeout quality (PDF)</button>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceReportsPage;
