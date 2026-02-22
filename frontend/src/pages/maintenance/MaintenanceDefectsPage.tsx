import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listAllDefects, type DefectRead } from "../../services/maintenance";
import { MaintenancePageShell, StatusPill } from "./components";

const MaintenanceDefectsPage: React.FC = () => {
  const [rows, setRows] = useState<DefectRead[]>([]);
  const navigate = useNavigate();
  useEffect(() => { listAllDefects().then(setRows).catch(() => setRows([])); }, []);
  return <MaintenancePageShell title="Defects">
    <div className="card" style={{ overflowX: "auto" }}>
      <table className="table"><thead><tr><th>Tail</th><th>Defect ref</th><th>Source</th><th>Severity</th><th>Status</th><th>Deferred?</th><th>Linked WO</th><th>Age</th></tr></thead>
      <tbody>{rows.map((d) => <tr key={d.id} style={{ cursor: "pointer" }} onClick={()=>navigate(`/maintenance/defects/${d.id}`)}><td>{d.aircraft_serial_number}</td><td>{d.operator_event_id || d.id}</td><td>{d.source}</td><td><StatusPill label={d.ata_chapter || "STD"} /></td><td>OPEN</td><td>No</td><td>{d.work_order_id || "-"}</td><td>{Math.floor((Date.now()-new Date(d.occurred_at).getTime())/86400000)}d</td></tr>)}</tbody></table>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceDefectsPage;
