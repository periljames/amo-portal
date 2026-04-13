import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { listAllDefects, type DefectRead } from "../../services/maintenance";
import { MaintenancePageShell, maintenanceActionAllowed } from "./components";

const MaintenanceDefectDetailPage: React.FC = () => {
  const { defectId } = useParams<{ defectId: string }>();
  const [defect, setDefect] = useState<DefectRead | null>(null);
  const canEdit = maintenanceActionAllowed("maintenance.update-task");

  useEffect(() => {
    listAllDefects().then((rows) => setDefect(rows.find((row) => String(row.id) === defectId) || null)).catch(() => setDefect(null));
  }, [defectId]);

  return (
    <MaintenancePageShell title={`Defect ${defect?.operator_event_id || defectId}`} requiredFeature="maintenance.defects">
      <div className="card" style={{ display: "grid", gap: 8 }}>
        <label>Description<textarea className="input" defaultValue={defect?.description || ""} disabled={!canEdit} /></label>
        <label>Troubleshooting notes<textarea className="input" placeholder="Enter notes" disabled={!canEdit} /></label>
        <label>Attachments<input className="input" placeholder="Paste attachment URL or reference" disabled={!canEdit} /></label>
        <label>Linked rectification WO<input className="input" defaultValue={defect?.work_order_id ? String(defect.work_order_id) : ""} disabled={!canEdit} /></label>
        <label>Deferral reference<input className="input" placeholder="TR deferral ID (optional)" disabled={!canEdit} /></label>
        <div><button className="btn btn-primary" disabled={!canEdit}>Save details</button></div>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceDefectDetailPage;
