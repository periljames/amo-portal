import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getWorkOrder, listTasksForWorkOrder, type TaskCardRead, type WorkOrderRead } from "../../services/workOrders";
import { listAllDefects, listInspections, listPartToolRequests } from "../../services/maintenance";
import { MaintenancePageShell, buildMaintenancePath, maintenanceActionAllowed } from "./components";

const tabs = ["Overview", "Tasks", "Findings/NR", "Parts/Tools", "Inspections", "Evidence", "Activity", "Audit Log"] as const;

const MaintenanceWorkOrderDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const { amoCode, woId } = useParams<{ amoCode?: string; woId: string }>();
  const id = Number(woId);
  const [wo, setWo] = useState<WorkOrderRead | null>(null);
  const [tasks, setTasks] = useState<TaskCardRead[]>([]);
  const [defects, setDefects] = useState<any[]>([]);
  const [active, setActive] = useState<(typeof tabs)[number]>("Overview");
  const canRaiseNr = maintenanceActionAllowed("maintenance.raise-non-routine");
  const canRequestParts = maintenanceActionAllowed("maintenance.request-parts");
  const canUpdateTask = maintenanceActionAllowed("maintenance.update-task");
  const canInspect = maintenanceActionAllowed("maintenance.perform-inspection");

  useEffect(() => {
    if (!id) return;
    getWorkOrder(id).then(setWo).catch(() => setWo(null));
    listTasksForWorkOrder(id).then(setTasks).catch(() => setTasks([]));
    listAllDefects()
      .then((rows) => setDefects(rows.filter((row) => row.work_order_id === id)))
      .catch(() => setDefects([]));
  }, [id]);

  const parts = listPartToolRequests().filter((p) => p.woId === id);
  const inspections = listInspections().filter((i) => i.woId === id);

  return (
    <MaintenancePageShell title={`WO ${wo?.wo_number || id}`} requiredFeature="maintenance.work-orders">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {tabs.map((tab) => (
          <button
            key={tab}
            className={`btn ${active === tab ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setActive(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="card">
        {active === "Overview" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(200px,1fr))", gap: 8 }}>
            <div><b>WO number</b><div>{wo?.wo_number}</div></div>
            <div><b>Tail</b><div>{wo?.aircraft_serial_number}</div></div>
            <div><b>Planned window</b><div>{wo?.open_date} → {wo?.due_date}</div></div>
            <div><b>Status</b><div>{wo?.status}</div></div>
            <div><b>Linked WP</b><div>{wo?.work_package_ref || "-"}</div></div>
            <div><b>Created</b><div>{wo?.created_at || "-"}</div></div>
          </div>
        )}
        {active === "Tasks" && (
          <table className="table">
            <thead><tr><th>Task title/ATA</th><th>Status</th><th>Assigned</th><th>Sign-off</th><th>Evidence</th></tr></thead>
            <tbody>
              {tasks.map((task) => (
                <tr
                  key={task.id}
                  style={{ cursor: canUpdateTask ? "pointer" : "default", opacity: canUpdateTask ? 1 : 0.8 }}
                  onClick={() => canUpdateTask && navigate(buildMaintenancePath(`tasks/${task.id}`, { amoCode }))}
                >
                  <td>{task.title} / {task.ata_chapter || "-"}</td>
                  <td>{task.status}</td>
                  <td>-</td>
                  <td>{task.status === "INSPECTED" ? "Yes" : "No"}</td>
                  <td>0</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {active === "Findings/NR" && (
          <div>
            <p>Defects and non-routines linked to this work order.</p>
            <div>Linked defects: {defects.length}</div>
            <button className="btn btn-secondary" disabled={!canRaiseNr} onClick={() => navigate(buildMaintenancePath("non-routines", { amoCode }))}>Open non-routines</button>
          </div>
        )}
        {active === "Parts/Tools" && (
          <div>
            <table className="table">
              <thead><tr><th>Type</th><th>Description</th><th>Qty</th><th>Status</th></tr></thead>
              <tbody>{parts.map((part) => <tr key={part.id}><td>{part.itemType}</td><td>{part.description}</td><td>{part.qty}</td><td>{part.status}</td></tr>)}</tbody>
            </table>
            {!canRequestParts ? <div className="text-muted">Only execution, certifying, supervisory, and stores roles can raise or update parts demand.</div> : null}
          </div>
        )}
        {active === "Inspections" && (
          <div>
            <table className="table">
              <thead><tr><th>Type</th><th>Required role</th><th>Status</th><th>Hold</th></tr></thead>
              <tbody>{inspections.map((inspection) => <tr key={inspection.id}><td>{inspection.inspectionType}</td><td>{inspection.requiredByRole}</td><td>{inspection.status}</td><td>{inspection.holdFlag ? "Yes" : "No"}</td></tr>)}</tbody>
            </table>
            {!canInspect ? <div className="text-muted">Only supervisory and certifying roles can close inspection holds.</div> : null}
          </div>
        )}
        {active === "Evidence" && (
          <div>
            <input className="input" placeholder="Add evidence link" disabled={!canUpdateTask} />
            <button className="btn btn-primary" style={{ marginLeft: 8 }} disabled={!canUpdateTask}>Attach</button>
          </div>
        )}
        {active === "Activity" && <div>Activity timeline ready for manual entries and API events.</div>}
        {active === "Audit Log" && <div>Audit log panel ready. Backend audit events can be wired by object id.</div>}
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceWorkOrderDetailPage;
