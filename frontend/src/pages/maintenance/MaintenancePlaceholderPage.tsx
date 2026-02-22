import React from "react";
import { Link, useLocation } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";

const TITLES: Record<string, string> = {
  "/maintenance/work-packages": "Work Package Execution",
  "/maintenance/defects": "Defects",
  "/maintenance/non-routines": "Non-Routines",
  "/maintenance/inspections": "Inspections & Holds",
  "/maintenance/parts-tools": "Parts & Tools Requests",
  "/maintenance/closeout": "Closeout",
  "/maintenance/reports": "Reports",
  "/maintenance/settings": "Maintenance Settings",
};

const MaintenancePlaceholderPage: React.FC = () => {
  const context = getContext();
  const location = useLocation();
  const amoCode = context.amoSlug || "system";
  const department = (context.department || "planning").toLowerCase();
  const title = TITLES[location.pathname] || "Maintenance";

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
      <div className="page-header">
        <h1 className="page-title">{title}</h1>
      </div>
      <div className="card" style={{ display: "grid", gap: 8 }}>
        <p>This view reuses existing Work, Fleet, CRS, and Audit services without duplicating domain models.</p>
        <p>Use the existing execution flow from Work Orders while this consolidated alias view stays route-compatible.</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="btn btn-primary" to={`/maintenance/${amoCode}/${department}/work-orders`}>Open Work Orders</Link>
          <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/${department}/crs/new`}>Open CRS</Link>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default MaintenancePlaceholderPage;
