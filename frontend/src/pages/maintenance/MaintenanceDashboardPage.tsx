import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listCRS } from "../../services/crs";
import { listInspections, listPartToolRequests } from "../../services/maintenance";
import { listWorkOrders, type WorkOrderRead } from "../../services/workOrders";
import { MaintenancePageShell } from "./components";

const MaintenanceDashboardPage: React.FC = () => {
  const [workOrders, setWorkOrders] = useState<WorkOrderRead[]>([]);
  const [crsPending, setCrsPending] = useState(0);
  useEffect(() => { listWorkOrders({ limit: 500 }).then(setWorkOrders).catch(() => setWorkOrders([])); listCRS(0, 200, true).then((rows) => setCrsPending(rows.length)).catch(() => setCrsPending(0)); }, []);
  const inspections = listInspections();
  const parts = listPartToolRequests();
  const tiles = useMemo(() => [
    { label: "AOG / critical items", value: workOrders.filter((w) => w.wo_type === "DEFECT").length, path: "/maintenance/work-orders" },
    { label: "Work Orders in progress", value: workOrders.filter((w) => w.status === "IN_PROGRESS").length, path: "/maintenance/work-orders" },
    { label: "Waiting parts", value: parts.filter((p) => p.status === "REQUESTED").length, path: "/maintenance/parts-tools" },
    { label: "QA/Inspection holds", value: inspections.filter((i) => i.holdFlag && i.status !== "DONE").length, path: "/maintenance/inspections" },
    { label: "CRS pending", value: crsPending, path: "/maintenance/closeout" },
  ], [workOrders, parts, inspections, crsPending]);

  return <MaintenancePageShell title="Maintenance Dashboard">
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
      {tiles.map((tile) => <Link key={tile.label} to={tile.path} className="card" style={{ textDecoration: "none", color: "inherit" }}><div style={{ fontSize: 13, opacity: 0.8 }}>{tile.label}</div><div style={{ fontSize: 28, fontWeight: 700 }}>{tile.value}</div></Link>)}
    </div>
  </MaintenancePageShell>;
};

export default MaintenanceDashboardPage;
