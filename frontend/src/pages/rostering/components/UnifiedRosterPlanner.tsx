import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ContextualHelp } from "../../../components/UI/ContextualHelp";
import { PrerequisiteDialog, type PrerequisiteItem } from "../../../components/UI/PrerequisiteDialog";
import { listBaseStations } from "../../../services/foundations";
import { listRosterPeriods, listShiftTemplates } from "../../../services/rostering";
import { RosterPlannerV2 } from "./RosterPlannerV2";

const REFERENCE_STALE_MS = 15 * 60_000;

export function UnifiedRosterPlanner() {
  const { amoCode = "UNKNOWN" } = useParams();
  const root = `/maintenance/${encodeURIComponent(amoCode)}`;
  const [prerequisiteDismissed, setPrerequisiteDismissed] = useState(false);

  const basesQuery = useQuery({
    queryKey: ["foundations", "base-stations", "active"],
    queryFn: () => listBaseStations(),
    staleTime: REFERENCE_STALE_MS,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
  });
  const shiftsQuery = useQuery({
    queryKey: ["rostering", "planner", "shift-templates", "active"],
    queryFn: () => listShiftTemplates(false),
    staleTime: REFERENCE_STALE_MS,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
  });
  const periodsQuery = useQuery({
    queryKey: ["rostering", "planner", "prerequisite-periods"],
    queryFn: () => listRosterPeriods(),
    staleTime: 2 * 60_000,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
  });

  const prerequisitesResolved = !basesQuery.isPending && !shiftsQuery.isPending && !periodsQuery.isPending;
  const prerequisiteItems = useMemo<PrerequisiteItem[]>(() => {
    const items: PrerequisiteItem[] = [];
    if (basesQuery.isSuccess && basesQuery.data.length === 0) {
      items.push({
        id: "bases",
        title: "Create at least one operating base",
        detail: "Duty cannot be assigned safely until an administrator creates the tenant's canonical bases and stations.",
        action: <Link className="portal-help-button portal-help-button--primary" to={`${root}/admin/amo-assets?section=operating-structure`}>Open operating structure</Link>,
      });
    }
    if (shiftsQuery.isSuccess && shiftsQuery.data.length === 0) {
      items.push({
        id: "shifts",
        title: "Create shift templates",
        detail: "Define reusable day, night, standby and off-duty windows before placing personnel on the roster.",
        action: <Link className="portal-help-button portal-help-button--primary" to={`${root}/rostering/settings?tab=shifts`}>Create shifts</Link>,
      });
    }
    if (periodsQuery.isSuccess && periodsQuery.data.length === 0) {
      items.push({
        id: "periods",
        title: "Create a planning period",
        detail: "The planner needs a dated period and a draft version before assignments can be created.",
        action: <Link className="portal-help-button portal-help-button--primary" to={`${root}/rostering/settings?tab=periods`}>Create period</Link>,
      });
    }
    return items;
  }, [basesQuery.data, basesQuery.isSuccess, periodsQuery.data, periodsQuery.isSuccess, root, shiftsQuery.data, shiftsQuery.isSuccess]);

  const prerequisiteOpen = prerequisitesResolved && prerequisiteItems.length > 0 && !prerequisiteDismissed;

  return (
    <div style={{ display: "grid", gap: "0.5rem", minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", minHeight: "2rem" }}>
        <ContextualHelp
          topic="rostering-source-commitments"
          version={1}
          autoOpen={prerequisitesResolved && prerequisiteItems.length === 0}
          triggerLabel="Explain roster commitments"
          title="Training, leave and Quality commitments"
          description="The planner shows source-owned commitments directly inside each person's date cells. Rostering does not duplicate or rewrite those records: approved leave remains in Workforce, training remains in Training and assigned audits remain in Quality."
          checklist={[
            "Blocking commitments prevent a conflicting duty assignment.",
            "Open the source module to change leave, training or Quality work.",
            "Use the help icon whenever this explanation is needed again.",
          ]}
          actions={<Link className="portal-help-button portal-help-button--secondary" to={`${root}/rostering/settings`}>Review integrations</Link>}
        />
      </div>

      {(basesQuery.error || shiftsQuery.error || periodsQuery.error) ? (
        <div className="wr-inline-warning" role="status">
          Some setup checks could not be completed. The planner remains available; retry the affected setup source instead of waiting on this page indefinitely.
        </div>
      ) : null}

      <RosterPlannerV2 />

      <PrerequisiteDialog
        open={prerequisiteOpen}
        items={prerequisiteItems}
        onClose={() => setPrerequisiteDismissed(true)}
      />
    </div>
  );
}
