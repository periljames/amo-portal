import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { listAllDefects, type DefectRead } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceDefectDetailPage: React.FC = () => {
  const { defectId } = useParams<{ defectId: string }>();
  const [defect, setDefect] = useState<DefectRead | null>(null);
  useEffect(() => { listAllDefects().then((x)=>setDefect(x.find((d)=>String(d.id)===defectId) || null)).catch(()=>setDefect(null)); }, [defectId]);
  return <MaintenancePageShell title={`Defect ${defect?.operator_event_id || defectId}`}>
    <div className="card" style={{ display: "grid", gap: 8 }}>
      <label>Description<textarea className="input" defaultValue={defect?.description || ""} /></label>
      <label>Troubleshooting notes<textarea className="input" placeholder="Enter notes" /></label>
      <label>Attachments<input className="input" placeholder="Paste attachment URL or reference" /></label>
      <label>Linked rectification WO<input className="input" defaultValue={defect?.work_order_id ? String(defect.work_order_id) : ""} /></label>
      <label>Deferral reference<input className="input" placeholder="TR deferral ID (optional)" /></label>
      <div><button className="btn btn-primary">Save details</button></div>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceDefectDetailPage;
