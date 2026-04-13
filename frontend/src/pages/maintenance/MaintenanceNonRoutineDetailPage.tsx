import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getMaintenanceSettings, listNonRoutines, saveNonRoutine, type NrStatus } from "../../services/maintenance";
import { MaintenancePageShell, maintenanceActionAllowed } from "./components";

const MaintenanceNonRoutineDetailPage: React.FC = () => {
  const { nrId } = useParams<{ nrId: string }>();
  const item = useMemo(() => listNonRoutines().find((row) => row.id === nrId), [nrId]);
  const [status, setStatus] = useState<NrStatus>(item?.status || "DRAFT");
  const [dispositionText, setDispositionText] = useState(item?.dispositionText || "");
  const [approver, setApprover] = useState(item?.approver || "");
  const canEdit = maintenanceActionAllowed("maintenance.raise-non-routine");

  const save = () => {
    if (!item || !canEdit) return;
    const settings = getMaintenanceSettings();
    if (settings.nrApprovalRequired && status === "CLOSED" && item.status !== "APPROVED") {
      alert("NR approval is required before closing.");
      return;
    }
    const ok = saveNonRoutine({ ...item, status, dispositionText, approver });
    if (!ok) {
      alert("Go Live is active. Demo/local NR editing is disabled.");
      return;
    }
    alert("NR updated");
  };

  if (!item) {
    return <MaintenancePageShell title="NR not found" requiredFeature="maintenance.non-routines"><div className="card">NR not found.</div></MaintenancePageShell>;
  }

  return (
    <MaintenancePageShell title={`Non-Routine ${item.id.slice(0, 8)}`} requiredFeature="maintenance.non-routines">
      <div className="card" style={{ display: "grid", gap: 8 }}>
        <div>Tail: {item.tail} · WO: {item.woId}</div>
        <textarea className="input" value={dispositionText} onChange={(e) => setDispositionText(e.target.value)} placeholder="Disposition text" disabled={!canEdit} />
        <input className="input" value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Approver" disabled={!canEdit} />
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value as NrStatus)} disabled={!canEdit}>{["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "EXECUTED", "CLOSED"].map((state) => <option key={state}>{state}</option>)}</select>
        <button className="btn btn-primary" onClick={save} disabled={!canEdit}>Save NR</button>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceNonRoutineDetailPage;
