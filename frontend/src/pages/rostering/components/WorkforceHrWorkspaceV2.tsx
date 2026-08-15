import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, ClipboardCheck, Layers3, UsersRound } from "lucide-react";

import { getWorkforceHrDashboard } from "../../../services/workforceHr";
import { errorMessage } from "../rosterUi";
import { RosterLoading } from "./RosterShell";
import { WorkforceBulkSetupPanel } from "./WorkforceBulkSetupPanel";
import { WorkforceGovernancePanel } from "./WorkforceGovernancePanel";
import { WorkforcePeopleDirectory } from "./WorkforcePeopleDirectory";
import "./workforce-hr-workspace.css";

const LazyWorkforceOperations = lazy(() => import("./WorkforceOperationsWorkspace")
  .then((module) => ({ default: module.WorkforceOperationsWorkspace })));

type WorkspaceSection = "people" | "governance" | "bulk" | "operations";
const WORKSPACE_SECTIONS = new Set<WorkspaceSection>(["people", "governance", "bulk", "operations"]);

function initialSection(): WorkspaceSection {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("workforce_view") as WorkspaceSection | null;
  if (requested && WORKSPACE_SECTIONS.has(requested)) return requested;
  if ([...params.keys()].some((key) => key.startsWith("bulk_"))) return "bulk";
  return "people";
}

export function WorkforceHrWorkspaceV2() {
  const [section, setSection] = useState<WorkspaceSection>(initialSection);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("workforce_view") === section) return;
    params.set("workforce_view", section);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}${window.location.hash}`);
  }, [section]);
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
  const selectSection = (next: WorkspaceSection) => {
    setSection(next);
    const params = new URLSearchParams(window.location.search);
    params.set("workforce_view", next);
    if (next !== "bulk") [...params.keys()].filter((key) => key.startsWith("bulk_")).forEach((key) => params.delete(key));
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}${window.location.hash}`);
  };
  return (
    <div className="hr-workspace-v2">
      <nav className="hr-workspace__nav" aria-label="Workforce workspace sections">
        <div className="hr-workspace__nav-heading"><span>Workforce</span><strong>Manage people</strong></div>
        <button type="button" aria-current={section === "people" ? "page" : undefined} className={section === "people" ? "is-active" : ""} onClick={() => selectSection("people")}><UsersRound size={17} /><span><strong>People & contracts</strong><small>Records, access and readiness</small></span></button>
        <button type="button" aria-current={section === "governance" ? "page" : undefined} className={section === "governance" ? "is-active" : ""} onClick={() => selectSection("governance")}><Building2 size={17} /><span><strong>Organization & roles</strong><small>Structure and reporting lines</small></span></button>
        <button type="button" aria-current={section === "bulk" ? "page" : undefined} className={section === "bulk" ? "is-active" : ""} onClick={() => selectSection("bulk")}><Layers3 size={17} /><span><strong>Batch setup</strong><small>Contracts and work patterns</small></span></button>
        <button type="button" aria-current={section === "operations" ? "page" : undefined} className={section === "operations" ? "is-active" : ""} onClick={() => selectSection("operations")}><ClipboardCheck size={17} /><span><strong>Leave, time & patterns</strong><small>Employee operations</small></span></button>
      </nav>
      <main className="hr-workspace-v2__content">
      {section === "people" ? (
        <WorkforcePeopleDirectory
          canManageContracts={dashboard.can_manage_contracts}
        />
      ) : null}

      {section === "governance" ? (
        <WorkforceGovernancePanel canManage={dashboard.can_manage_contracts} />
      ) : null}

      {section === "bulk" ? (
        <WorkforceBulkSetupPanel
          canManageContracts={dashboard.can_manage_contracts}
          canManagePatterns={dashboard.can_assign_patterns}
        />
      ) : null}

      {section === "operations" ? (
        <div className="hr-operations-shell">
          <Suspense fallback={<RosterLoading label="Opening Workforce operations…" />}>
            <LazyWorkforceOperations />
          </Suspense>
        </div>
      ) : null}
      </main>
    </div>
  );
}
