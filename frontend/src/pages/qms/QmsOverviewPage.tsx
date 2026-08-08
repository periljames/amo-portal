import React from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsOperationalControlCentre from "./QmsOperationalControlCentre";
import QmsWorkspaceBridgePage from "./QmsWorkspaceBridgePage";
import type { QmsWorkspaceId } from "./routes/qmsWorkspaceRegistry";

function decodeSegment(value: string | undefined): string {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function amoCodeFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  return parts[0] === "maintenance" ? decodeSegment(parts[1]) : "";
}

function requestedWorkspace(search: string): QmsWorkspaceId {
  const query = new URLSearchParams(search);
  const requested = query.get("workspace");
  if (["missions", "people", "assurance", "intelligence", "planner"].includes(requested || "")) {
    return requested as QmsWorkspaceId;
  }
  const legacyHub = query.get("hub");
  if (legacyHub === "intelligence") return "intelligence";
  if (legacyHub === "controls" || legacyHub === "evidence") return "assurance";
  return "control-room";
}

const QmsOverviewPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const amoCode = params.amoCode || amoCodeFromPath(location.pathname) || "UNKNOWN";
  const workspace = requestedWorkspace(location.search);

  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission("qms.dashboard.view")) {
    return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}`} replace />;
  }

  if (workspace === "planner") {
    return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}/quality/calendar/month`} replace />;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      {workspace === "control-room"
        ? <QmsOperationalControlCentre amoCode={amoCode} />
        : <QmsWorkspaceBridgePage amoCode={amoCode} workspace={workspace} />}
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
