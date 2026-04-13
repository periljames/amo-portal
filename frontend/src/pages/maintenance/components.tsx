import React from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import { usePortalRuntimeMode } from "../../hooks/usePortalRuntimeMode";
import {
  canPerformAction,
  canViewFeature,
  formatCapabilitiesForUi,
  type ModuleFeature,
} from "../../utils/roleAccess";

export const StatusPill: React.FC<{ label: string }> = ({ label }) => (
  <span
    style={{
      padding: "2px 10px",
      borderRadius: 999,
      background: "#eef2ff",
      fontSize: 12,
      fontWeight: 600,
    }}
  >
    {label}
  </span>
);

const tabs: Array<{ label: string; suffix: string; feature: ModuleFeature }> = [
  { label: "Dashboard", suffix: "dashboard", feature: "maintenance.dashboard" },
  { label: "Work Orders", suffix: "work-orders", feature: "maintenance.work-orders" },
  { label: "Work Packages", suffix: "work-packages", feature: "maintenance.work-packages" },
  { label: "Defects", suffix: "defects", feature: "maintenance.defects" },
  { label: "Non-Routines", suffix: "non-routines", feature: "maintenance.non-routines" },
  { label: "Inspections", suffix: "inspections", feature: "maintenance.inspections" },
  { label: "Parts/Tools", suffix: "parts-tools", feature: "maintenance.parts-tools" },
  { label: "Closeout", suffix: "closeout", feature: "maintenance.closeout" },
  { label: "Reports", suffix: "reports", feature: "maintenance.reports" },
  { label: "Settings", suffix: "settings", feature: "maintenance.settings" },
];

export const MaintenancePermissionNotice: React.FC<{ text: string }> = ({ text }) => (
  <div className="card" style={{ marginBottom: 12, borderLeft: "4px solid #f59e0b" }}>
    <strong>Role visibility</strong>
    <div className="text-muted" style={{ marginTop: 6 }}>
      {text}
    </div>
  </div>
);

export const MaintenancePageShell: React.FC<{
  title: string;
  children: React.ReactNode;
  requiredFeature?: ModuleFeature;
  notice?: string | null;
}> = ({ title, children, requiredFeature, notice }) => {
  const ctx = getContext();
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const { isGoLive } = usePortalRuntimeMode();
  const currentUser = getCachedUser();
  const amoCode = params.amoCode || ctx.amoSlug || "system";
  const userCapabilities = formatCapabilitiesForUi(currentUser, ctx.department);
  const visibleTabs = tabs.filter((tab) => canViewFeature(currentUser, tab.feature, ctx.department));

  if (requiredFeature && !canViewFeature(currentUser, requiredFeature, ctx.department)) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="maintenance">
        <div className="page-header">
          <h1 className="page-title">{title}</h1>
        </div>
        <MaintenancePermissionNotice text="This maintenance surface is limited to maintenance execution, supervisory, and certifying roles." />
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="maintenance">
      <div
        className="page-header"
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}
      >
        <div>
          <h1 className="page-title">{title}</h1>
          <div className="text-muted" style={{ marginTop: 4 }}>
            Active role scope: {userCapabilities.join(" · ") || "Unassigned"}
          </div>
        </div>
        <StatusPill label={isGoLive ? "LIVE DATA MODE" : "DEMO DATA MODE"} />
      </div>
      {!isGoLive ? (
        <div className="card" style={{ marginBottom: 10 }}>
          Demo mode is active. Maintenance forms use demo/local data. Switch to REAL + Go Live in Admin to lock demo data off.
        </div>
      ) : null}
      {notice ? <MaintenancePermissionNotice text={notice} /> : null}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {visibleTabs.map((tab) => {
          const path = `/maintenance/${amoCode}/maintenance/${tab.suffix}`;
          return (
            <Link
              key={path}
              to={path}
              className={`btn ${location.pathname.startsWith(path) ? "btn-primary" : "btn-secondary"}`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
      {children}
    </DepartmentLayout>
  );
};


export function buildMaintenancePath(path: string, options?: { amoCode?: string | null }): string {
  const ctx = getContext();
  const amoCode = (options?.amoCode || ctx.amoSlug || "system").trim();
  const normalizedPath = path.replace(/^\/+/, "");
  return `/maintenance/${amoCode}/maintenance/${normalizedPath}`;
}

export function maintenanceActionAllowed(action: Parameters<typeof canPerformAction>[1]): boolean {
  return canPerformAction(getCachedUser(), action, getContext().department);
}
