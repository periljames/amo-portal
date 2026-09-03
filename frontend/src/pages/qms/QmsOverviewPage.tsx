import React from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QualityExcellenceCockpit from "../../components/QMS/QualityExcellenceCockpit";
import QmsAssurancePage from "./QmsAssurancePage";
import QmsIntelligencePage from "./QmsIntelligencePage";
import QmsMissionsPage from "./QmsMissionsPage";
import QmsOperationalControlCentre from "./QmsOperationalControlCentre";
import QmsPeoplePage from "./QmsPeoplePage";
import { QMS_WORKSPACES, type QmsWorkspaceId } from "./routes/qmsWorkspaceRegistry";

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

function assuranceHub(search: string): "controls" | "evidence" | "intelligence" | null {
  const requested = new URLSearchParams(search).get("hub");
  return requested === "controls" || requested === "evidence" || requested === "intelligence" ? requested : null;
}

function requestedWorkspace(search: string): QmsWorkspaceId {
  const requested = new URLSearchParams(search).get("workspace");
  if (["missions", "people", "assurance", "intelligence", "planner"].includes(requested || "")) {
    return requested as QmsWorkspaceId;
  }
  return "control-room";
}

function workspacePermission(workspace: QmsWorkspaceId): string {
  return QMS_WORKSPACES.find((definition) => definition.id === workspace)?.permission || "qms.dashboard.view";
}

const QmsOverviewPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const amoCode = params.amoCode || amoCodeFromPath(location.pathname) || "UNKNOWN";
  const hub = assuranceHub(location.search);
  const workspace = requestedWorkspace(location.search);
  const qualityRoot = `/maintenance/${encodeURIComponent(amoCode)}/quality`;

  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission("qms.dashboard.view")) {
    return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}`} replace />;
  }

  if (!hub && !hasQmsRolePermission(workspacePermission(workspace))) {
    return <Navigate to={qualityRoot} replace />;
  }

  if (workspace === "planner") {
    return <Navigate to={`${qualityRoot}/calendar/week`} replace />;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      {hub
        ? <QualityExcellenceCockpit amoCode={amoCode} />
        : workspace === "control-room"
          ? <QmsOperationalControlCentre amoCode={amoCode} />
          : workspace === "missions"
            ? <QmsMissionsPage amoCode={amoCode} />
            : workspace === "people"
              ? <QmsPeoplePage amoCode={amoCode} />
              : workspace === "assurance"
                ? <QmsAssurancePage amoCode={amoCode} />
                : <QmsIntelligencePage amoCode={amoCode} />}
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
