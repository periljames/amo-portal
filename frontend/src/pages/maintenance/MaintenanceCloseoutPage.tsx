import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { listWorkOrders, listTasksForWorkOrder, type WorkOrderRead } from "../../services/workOrders";
import { getMaintenanceSettings, listInspections } from "../../services/maintenance";
import { MaintenancePageShell, buildMaintenancePath, maintenanceActionAllowed } from "./components";

const MaintenanceCloseoutPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode } = useParams<{ amoCode?: string }>();
  const [rows, setRows] = useState<WorkOrderRead[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [checks, setChecks] = useState({ tasksDone: false, holdsReleased: false, inspectionsDone: false, evidenceOk: true });
  const canCloseout = maintenanceActionAllowed("maintenance.closeout");

  useEffect(() => {
    listWorkOrders({ limit: 500 }).then(setRows).catch(() => setRows([]));
  }, []);

  const validate = async (workOrderId: number) => {
    const tasks = await listTasksForWorkOrder(workOrderId).catch(() => []);
    const holds = listInspections().filter((item) => item.woId === workOrderId && item.holdFlag);
    const inspections = listInspections().filter((item) => item.woId === workOrderId);
    const settings = getMaintenanceSettings();
    setChecks({
      tasksDone: tasks.length > 0 && tasks.every((task) => task.status === "COMPLETED" || task.status === "INSPECTED"),
      holdsReleased: holds.every((hold) => hold.status === "DONE"),
      inspectionsDone: inspections.every((inspection) => inspection.status === "DONE"),
      evidenceOk: !settings.evidenceRequiredToCloseTask,
    });
  };

  return (
    <MaintenancePageShell title="Closeout & CRS Pending" requiredFeature="maintenance.closeout">
      <div className="card" style={{ marginBottom: 12 }}>
        <select className="input" value={selected || ""} onChange={(e) => { const id = Number(e.target.value); setSelected(id); validate(id); }}>
          <option value="">Select WO</option>
          {rows.map((workOrder) => <option key={workOrder.id} value={workOrder.id}>{workOrder.wo_number} ({workOrder.status})</option>)}
        </select>
        <ul>
          <li>All required tasks completed: {checks.tasksDone ? "✅" : "❌"}</li>
          <li>All holds released: {checks.holdsReleased ? "✅" : "❌"}</li>
          <li>Required inspections completed: {checks.inspectionsDone ? "✅" : "❌"}</li>
          <li>Evidence settings satisfied: {checks.evidenceOk ? "✅" : "❌"}</li>
        </ul>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" disabled={!canCloseout || !selected || !(checks.tasksDone && checks.holdsReleased && checks.inspectionsDone && checks.evidenceOk)} onClick={() => navigate(buildMaintenancePath("crs/new", { amoCode }))}>Issue CRS</button>
        </div>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceCloseoutPage;
