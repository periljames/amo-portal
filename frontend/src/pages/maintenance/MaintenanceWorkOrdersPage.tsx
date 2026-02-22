import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listWorkOrders, type WorkOrderRead } from "../../services/workOrders";
import { listPartToolRequests, listInspections } from "../../services/maintenance";
import { MaintenancePageShell, StatusPill } from "./components";

const MaintenanceWorkOrdersPage: React.FC = () => {
  const [rows, setRows] = useState<WorkOrderRead[]>([]);
  const navigate = useNavigate();
  useEffect(() => { listWorkOrders({ limit: 500 }).then(setRows).catch(() => setRows([])); }, []);
  const holds = listInspections().filter((x) => x.holdFlag && x.status !== "DONE");
  const parts = listPartToolRequests();
  return <MaintenancePageShell title="Maintenance Work Orders">
    <div className="card" style={{ overflowX: "auto" }}>
      <table className="table">
        <thead><tr><th>WO number</th><th>Tail</th><th>Priority</th><th>Status</th><th>Open date</th><th>Target close</th><th>Holds</th><th>Parts waiting</th><th>CRS status</th></tr></thead>
        <tbody>
          {rows.map((wo) => {
            const holdCount = holds.filter((h) => h.woId === wo.id).length;
            const partCount = parts.filter((p) => p.woId === wo.id && p.status === "REQUESTED").length;
            return <tr key={wo.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/maintenance/work-orders/${wo.id}`)}>
              <td>{wo.wo_number}</td><td>{wo.aircraft_serial_number}</td><td><StatusPill label={(wo.wo_type || "PERIODIC").toString()} /></td><td>{wo.status}</td><td>{wo.open_date || "-"}</td><td>{wo.due_date || "-"}</td><td>{holdCount}</td><td>{partCount}</td><td>{wo.status === "INSPECTED" ? "Pending" : "-"}</td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceWorkOrdersPage;
