import { lazy, Suspense, useState } from "react";
import { BarChart3, UsersRound } from "lucide-react";

import { RosterLoading } from "./RosterShell";

const LazyCapacityBoard = lazy(() => import("./CapacityBoard").then((module) => ({ default: module.CapacityBoard })));
const LazyRosterReports = lazy(() => import("./RosterReports").then((module) => ({ default: module.RosterReports })));

type View = "capacity" | "reports";

export function RosterOperationsWorkspace() {
  const [view, setView] = useState<View>("capacity");
  return (
    <div className="wr-settings">
      <div className="wr-settings-tabs" role="tablist" aria-label="Rostering operations views">
        <button type="button" role="tab" aria-selected={view === "capacity"} className={view === "capacity" ? "is-active" : ""} onClick={() => setView("capacity")}><UsersRound size={16} /> Capacity & coverage</button>
        <button type="button" role="tab" aria-selected={view === "reports"} className={view === "reports" ? "is-active" : ""} onClick={() => setView("reports")}><BarChart3 size={16} /> Reports & reconciliation</button>
      </div>
      <Suspense fallback={<RosterLoading label="Opening operations workspace…" />}>
        {view === "capacity" ? <LazyCapacityBoard /> : <LazyRosterReports />}
      </Suspense>
    </div>
  );
}
