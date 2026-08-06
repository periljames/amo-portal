import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, UsersRound } from "lucide-react";

import { getWorkforceHrDashboard } from "../../../services/workforceHr";
import { errorMessage } from "../rosterUi";
import { RosterLoading } from "./RosterShell";
import { WorkforcePeopleDirectory } from "./WorkforcePeopleDirectory";

const LazyWorkforceOperations = lazy(() => import("./WorkforceOperationsWorkspace")
  .then((module) => ({ default: module.WorkforceOperationsWorkspace })));

type WorkspaceSection = "people" | "operations";

export function WorkforceHrWorkspaceV2() {
  const [section, setSection] = useState<WorkspaceSection>("people");
  const accessQuery = useQuery({
    queryKey: ["workforce", "hr", "dashboard", "access"],
    queryFn: () => getWorkforceHrDashboard(1),
    staleTime: 60_000,
  });

  if (accessQuery.isPending) return <RosterLoading label="Opening Workforce controls…" />;
  if (accessQuery.error || !accessQuery.data) {
    return <div className="wr-inline-error">{errorMessage(accessQuery.error || new Error("Workforce controls unavailable"))}</div>;
  }

  const dashboard = accessQuery.data;
  return (
    <div className="hr-workspace-v2">
      <nav className="hr-workspace__nav" aria-label="Workforce workspace sections">
        <button type="button" className={section === "people" ? "is-active" : ""} onClick={() => setSection("people")}><UsersRound size={15} /> People & contracts</button>
        <button type="button" className={section === "operations" ? "is-active" : ""} onClick={() => setSection("operations")}><ClipboardCheck size={15} /> Leave, time & patterns</button>
      </nav>

      {section === "people" ? (
        <WorkforcePeopleDirectory
          canManageContracts={dashboard.can_manage_contracts}
          canInitializeDefaults={dashboard.can_initialize_default_day_pattern}
        />
      ) : null}

      {section === "operations" ? (
        <div className="hr-operations-shell">
          <Suspense fallback={<RosterLoading label="Opening Workforce operations…" />}>
            <LazyWorkforceOperations />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}
