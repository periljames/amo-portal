import React from "react";
import { listWorkOrders } from "../../services/workOrders";
import { listAllDefects } from "../../services/maintenance";
import { MaintenancePageShell } from "./components";

const MaintenanceReportsPage: React.FC = () => {
  const workOrders = listWorkOrders({ limit: 500 });
  const defectsPromise = listAllDefects();

  return (
    <MaintenancePageShell title="Maintenance Reports" requiredFeature="maintenance.reports">
      <div className="card">
        <p className="text-muted">Operational reporting for execution, defect ageing, and inspection throughput.</p>
        <ul>
          <li>Work order register source: {Array.isArray(workOrders) ? workOrders.length : "live"}</li>
          <li>Defect register source: {defectsPromise ? "connected" : "unavailable"}</li>
          <li>Suitable for supervisors, certifying staff, technicians, and quality review.</li>
        </ul>
      </div>
    </MaintenancePageShell>
  );
};

export default MaintenanceReportsPage;
