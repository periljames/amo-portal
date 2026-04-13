import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { listAllDefects, type DefectRead } from "../../services/maintenance";
import { MaintenancePageShell, StatusPill, buildMaintenancePath } from "./components";

const MaintenanceDefectsPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode } = useParams<{ amoCode?: string }>();
  const [rows, setRows] = useState<DefectRead[]>([]);

  useEffect(() => {
    listAllDefects().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <MaintenancePageShell title="Defects" requiredFeature="maintenance.defects">
      <div className="card" style={{ overflowX: "auto" }}>
        <table className="table">
          <thead><tr><th>Tail</th><th>Defect ref</th><th>Source</th><th>Severity</th><th>Status</th><th>Deferred?</th><th>Linked WO</th><th>Age</th></tr></thead>
          <tbody>
            {rows.map((defect) => (
              <tr key={defect.id} style={{ cursor: "pointer" }} onClick={() => navigate(buildMaintenancePath(`defects/${defect.id}`, { amoCode }))}>
                <td>{defect.aircraft_serial_number}</td>
                <td>{defect.operator_event_id || defect.id}</td>
                <td>{defect.source}</td>
                <td><StatusPill label={defect.ata_chapter || "STD"} /></td>
                <td>OPEN</td>
                <td>No</td>
                <td>{defect.work_order_id || "-"}</td>
                <td>{Math.floor((Date.now() - new Date(defect.occurred_at).getTime()) / 86400000)}d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceDefectsPage;
