import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getMaintenanceSettings, listNonRoutines, saveNonRoutine, type NrStatus } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceNonRoutineDetailPage: React.FC = () => {
  const { nrId } = useParams<{ nrId: string }>();
  const item = useMemo(() => listNonRoutines().find((x) => x.id === nrId), [nrId]);
  const [status, setStatus] = useState<NrStatus>(item?.status || "DRAFT");
  const [dispositionText, setDispositionText] = useState(item?.dispositionText || "");
  const [approver, setApprover] = useState(item?.approver || "");
  const save = () => {
    if (!item) return;
    const settings = getMaintenanceSettings();
    if (settings.nrApprovalRequired && status === "CLOSED" && item.status !== "APPROVED") {
      alert("NR approval is required before closing."); return;
    }
    saveNonRoutine({ ...item, status, dispositionText, approver });
    alert("NR updated");
  };
  if (!item) return <MaintenancePageShell title="NR not found"><div className="card">NR not found.</div></MaintenancePageShell>;
  return <MaintenancePageShell title={`Non-Routine ${item.id.slice(0, 8)}`}>
    <div className="card" style={{display:"grid", gap:8}}>
      <div>Tail: {item.tail} · WO: {item.woId}</div>
      <textarea className="input" value={dispositionText} onChange={(e)=>setDispositionText(e.target.value)} placeholder="Disposition text" />
      <input className="input" value={approver} onChange={(e)=>setApprover(e.target.value)} placeholder="Approver" />
      <select className="input" value={status} onChange={(e)=>setStatus(e.target.value as NrStatus)}>{["DRAFT","SUBMITTED","APPROVED","REJECTED","EXECUTED","CLOSED"].map((s)=><option key={s}>{s}</option>)}</select>
      <button className="btn btn-primary" onClick={save}>Save NR</button>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceNonRoutineDetailPage;
