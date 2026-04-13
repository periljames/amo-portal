import React, { useEffect, useMemo, useState } from "react";
import { listWorkOrders, listTasksForWorkOrder, type WorkOrderRead } from "../../services/workOrders";
import { listInspections } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceWorkPackagesPage: React.FC = () => {
  const [workOrders, setWorkOrders] = useState<WorkOrderRead[]>([]);
  const [progress, setProgress] = useState<Record<number, number>>({});

  useEffect(() => {
    listWorkOrders({ limit: 500 })
      .then(async (rows) => {
        setWorkOrders(rows);
        const nextProgress: Record<number, number> = {};
        for (const workOrder of rows) {
          const tasks = await listTasksForWorkOrder(workOrder.id).catch(() => []);
          nextProgress[workOrder.id] = tasks.length
            ? Math.round((tasks.filter((task) => task.status === "COMPLETED" || task.status === "INSPECTED").length / tasks.length) * 100)
            : 0;
        }
        setProgress(nextProgress);
      })
      .catch(() => setWorkOrders([]));
  }, []);

  const holds = listInspections().filter((inspection) => inspection.holdFlag && inspection.status !== "DONE");
  const grouped = useMemo(
    () =>
      workOrders.reduce<Record<string, WorkOrderRead[]>>((acc, workOrder) => {
        const key = workOrder.work_package_ref || "UNASSIGNED";
        (acc[key] ||= []).push(workOrder);
        return acc;
      }, {}),
    [workOrders]
  );

  return (
    <MaintenancePageShell title="Work Package Execution" requiredFeature="maintenance.work-packages">
      {Object.entries(grouped).map(([workPackage, rows]) => (
        <div className="card" key={workPackage} style={{ marginBottom: 12 }}>
          <h3>{workPackage}</h3>
          <table className="table">
            <thead><tr><th>WO</th><th>Tail</th><th>Progress</th><th>Holds</th></tr></thead>
            <tbody>
              {rows.map((workOrder) => (
                <tr key={workOrder.id}>
                  <td>{workOrder.wo_number}</td>
                  <td>{workOrder.aircraft_serial_number}</td>
                  <td>{progress[workOrder.id] || 0}%</td>
                  <td>{holds.filter((hold) => hold.woId === workOrder.id).length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </MaintenancePageShell>
  );
};

export default MaintenanceWorkPackagesPage;
