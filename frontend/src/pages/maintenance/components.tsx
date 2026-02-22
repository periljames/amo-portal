import React from "react";
import { Link, useLocation } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getContext } from "../../services/auth";
import { usePortalRuntimeMode } from "../../hooks/usePortalRuntimeMode";

export const StatusPill: React.FC<{ label: string }> = ({ label }) => (
  <span style={{ padding: "2px 10px", borderRadius: 999, background: "#eef2ff", fontSize: 12, fontWeight: 600 }}>{label}</span>
);

const tabs = [["Dashboard","/maintenance"],["Work Orders","/maintenance/work-orders"],["Work Packages","/maintenance/work-packages"],["Defects","/maintenance/defects"],["Non-Routines","/maintenance/non-routines"],["Inspections","/maintenance/inspections"],["Parts/Tools","/maintenance/parts-tools"],["Closeout","/maintenance/closeout"],["Reports","/maintenance/reports"],["Settings","/maintenance/settings"]] as const;

export const MaintenancePageShell: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => {
  const ctx = getContext();
  const location = useLocation();
  const { isGoLive } = usePortalRuntimeMode();
  const amoCode = ctx.amoSlug || "system";
  const department = (ctx.department || "planning").toLowerCase();
  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department}>
      <div className="page-header" style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10}}>
        <h1 className="page-title">{title}</h1>
        <StatusPill label={isGoLive ? "LIVE DATA MODE" : "DEMO DATA MODE"} />
      </div>
      {!isGoLive ? <div className="card" style={{ marginBottom: 10 }}>Demo mode is active. Maintenance forms use demo/local data. Switch to REAL + Go Live in Admin to lock demo data off.</div> : null}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {tabs.map(([label, path]) => (<Link key={path} to={path} className={`btn ${location.pathname.startsWith(path) ? "btn-primary" : "btn-secondary"}`}>{label}</Link>))}
      </div>
      {children}
    </DepartmentLayout>
  );
};
