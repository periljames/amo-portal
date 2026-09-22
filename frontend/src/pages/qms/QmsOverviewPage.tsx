import React, { lazy, Suspense, useEffect } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsOperationalControlCentre from "./QmsOperationalControlCentre";
import { QMS_WORKSPACES, qmsWorkspaceEntryPath, type QmsWorkspaceId } from "./routes/qmsWorkspaceRegistry";
import { qmsPageLoaders } from "../../app/qmsRouteLoaders";
import { scheduleWorkspaceRoutePreload } from "../../app/routePreload";
import WorkspaceLoading from "../../components/shared/WorkspaceLoading";

const QualityExcellenceCockpit = lazy(qmsPageLoaders.assuranceHub);
const QmsIntelligencePage = lazy(qmsPageLoaders.intelligence);
const QmsMissionsPage = lazy(qmsPageLoaders.missions);
const QmsPeoplePage = lazy(qmsPageLoaders.people);

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

export type AssuranceHubId = "readiness" | "controls" | "evidence" | "intelligence";

/** Continuous Assurance cockpit hubs. Bare `/quality` (no hub) remains Control Room. */
export function assuranceHub(search: string): AssuranceHubId | null {
  const requested = new URLSearchParams(search).get("hub");
  return requested === "readiness"
    || requested === "controls"
    || requested === "evidence"
    || requested === "intelligence"
    ? requested
    : null;
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
  useEffect(() => scheduleWorkspaceRoutePreload(QMS_WORKSPACES
    .filter((item) => hasQmsRolePermission(item.permission))
    .map((item) => qmsWorkspaceEntryPath(amoCode, item.id))), [amoCode]);

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

  if (workspace === "assurance") {
    return <Navigate to={`${qualityRoot}/audits/register`} replace />;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <Suspense fallback={<WorkspaceLoading />}>
      {hub
        ? <QualityExcellenceCockpit amoCode={amoCode} />
        : workspace === "control-room"
          ? <QmsOperationalControlCentre amoCode={amoCode} />
          : workspace === "missions"
            ? <QmsMissionsPage amoCode={amoCode} />
            : workspace === "people"
              ? <QmsPeoplePage amoCode={amoCode} />
              : <QmsIntelligencePage amoCode={amoCode} />}
      </Suspense>
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
