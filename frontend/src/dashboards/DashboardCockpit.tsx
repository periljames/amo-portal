import React from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { getContext } from "../services/auth";

/**
 * Compatibility boundary for the superseded Quality cockpit.
 *
 * DashboardPage still imports this symbol while the shared department dashboard
 * is being decomposed. The old cockpit, manpower carousel, route catalogue, and
 * unofficial quality score are intentionally removed. Any remaining invocation
 * is redirected to the canonical operational Quality overview.
 */
const DashboardCockpit: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const context = getContext();
  const parts = location.pathname.split("/").filter(Boolean);
  const amoCode = params.amoCode || (parts[0] === "maintenance" ? parts[1] : "") || context.amoSlug || context.amoCode || "UNKNOWN";
  const target = `/maintenance/${encodeURIComponent(amoCode)}/quality`;

  if (location.pathname === target) {
    return (
      <div className="page-loading" role="status" aria-live="polite">
        <div className="page-loading__card">Opening the canonical Quality overview…</div>
      </div>
    );
  }

  return <Navigate to={target} replace />;
};

export default DashboardCockpit;
