import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { listInspections, saveInspection, type InspectionStatus } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceInspectionDetailPage: React.FC = () => {
  const { inspectionId } = useParams<{ inspectionId: string }>();
  const inspection = useMemo(()=>listInspections().find((x)=>x.id===inspectionId), [inspectionId]);
  const [status, setStatus] = useState<InspectionStatus>(inspection?.status || "REQUESTED");
  const [findings, setFindings] = useState(inspection?.findings || "");
  if (!inspection) return <MaintenancePageShell title="Inspection"><div className="card">Inspection not found.</div></MaintenancePageShell>;
  return <MaintenancePageShell title={`Inspection ${inspection.id.slice(0,8)}`}>
    <div className="card" style={{display:"grid", gap:8}}>
      <div>WO {inspection.woId} · Tail {inspection.tail}</div>
      <select className="input" value={status} onChange={(e)=>setStatus(e.target.value as InspectionStatus)}>{["REQUESTED","SCHEDULED","DONE","FAILED"].map((s)=><option key={s}>{s}</option>)}</select>
      <textarea className="input" value={findings} onChange={(e)=>setFindings(e.target.value)} placeholder="Findings"/>
      <label><input type="checkbox" checked={inspection.holdFlag} onChange={(e)=>{ const ok = saveInspection({ ...inspection, holdFlag: e.target.checked, status, findings }); if (!ok) alert("Go Live is active. Demo/local inspection editing is disabled."); }}/> Hold flag</label>
      <button className="btn btn-primary" onClick={()=>{ const ok = saveInspection({ ...inspection, status, findings }); if (!ok) { alert("Go Live is active. Demo/local inspection editing is disabled."); return; } alert('Inspection updated'); }}>Save inspection</button>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceInspectionDetailPage;
