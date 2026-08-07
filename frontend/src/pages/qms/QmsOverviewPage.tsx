import React from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QualityExcellenceCockpit from "../../components/QMS/QualityExcellenceCockpit";
import QmsOperationalControlCentre from "./QmsOperationalControlCentre";

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

const QmsOverviewPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const amoCode = params.amoCode || amoCodeFromPath(location.pathname) || "UNKNOWN";
  const hub = assuranceHub(location.search);

  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission("qms.dashboard.view")) {
    return <Navigate to={`/maintenance/${encodeURIComponent(amoCode)}`} replace />;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      {hub ? <QualityExcellenceCockpit amoCode={amoCode} /> : <QmsOperationalControlCentre amoCode={amoCode} />}
    </DepartmentLayout>
  );
};

export default QmsOverviewPage;
