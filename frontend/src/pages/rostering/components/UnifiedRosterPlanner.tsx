import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HelpCircle, X } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { PrerequisiteDialog, type PrerequisiteItem } from "../../../components/UI/PrerequisiteDialog";
import "../../../components/UI/contextual-help.css";
import { acknowledgeGuidance, guidanceAcknowledged } from "../../../services/contextualGuidance";
import { listRosterBaseStations } from "../../../services/rosterBases";
import { listRosterPeriods, listShiftTemplates } from "../../../services/rostering";
import { RosterPlannerV2 } from "./RosterPlannerV2";

const REFERENCE_STALE_MS = 15 * 60_000;
const HELP_TOPIC = "rostering-source-commitments";
const HELP_VERSION = 1;

function PlannerCommitmentHelp({ autoOpen, settingsRoute }: { autoOpen: boolean; settingsRoute: string }) {
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let active = true;
    if (!autoOpen) return () => { active = false; };
    void guidanceAcknowledged(HELP_TOPIC, HELP_VERSION).then((acknowledged) => {
      if (active && !acknowledged) setOpen(true);
    });
    return () => { active = false; };
  }, [autoOpen]);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      globalThis.setTimeout(() => (previousFocusRef.current || triggerRef.current)?.focus(), 0);
    };
  }, [open]);

  const acknowledge = async () => {
    setOpen(false);
    await acknowledgeGuidance(HELP_TOPIC, HELP_VERSION);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="portal-help-trigger"
        aria-label="Explain roster commitments"
        title="Explain roster commitments"
        onClick={() => setOpen(true)}
      >
        <HelpCircle size={17} aria-hidden="true" />
      </button>
      {open ? (
        <div className="portal-help-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setOpen(false);
        }}>
          <section className="portal-help-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
            <header className="portal-help-dialog__header">
              <div><span className="portal-help-dialog__eyebrow">Quick guidance</span><h2 id={titleId}>Training, leave and Quality commitments</h2></div>
              <button ref={closeRef} type="button" className="portal-help-dialog__close" onClick={() => setOpen(false)} aria-label="Close help without acknowledging"><X size={19} /></button>
            </header>
            <div className="portal-help-dialog__body">
              <p>The planner shows source-owned commitments directly inside each person's date cells. Rostering does not duplicate or rewrite those records: approved leave remains in Workforce, training remains in Training and assigned audits remain in Quality.</p>
              <ul>
                <li>Blocking commitments prevent a conflicting duty assignment.</li>
                <li>Open the source module to change leave, training or Quality work.</li>
                <li>Use the help icon whenever this explanation is needed again.</li>
              </ul>
            </div>
            <footer className="portal-help-dialog__footer">
              <Link className="portal-help-button portal-help-button--secondary" to={settingsRoute}>Review integrations</Link>
              <button type="button" className="portal-help-button portal-help-button--primary" onClick={() => void acknowledge()}>Got it</button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

export function UnifiedRosterPlanner() {
  const { amoCode = "UNKNOWN" } = useParams();
  const root = `/maintenance/${encodeURIComponent(amoCode)}`;
  const plannerRoute = `${root}/rostering/calendar`;
  const returnTo = encodeURIComponent(plannerRoute);
  const [prerequisiteDismissed, setPrerequisiteDismissed] = useState(false);

  const basesQuery = useQuery({
    queryKey: ["foundations", "base-stations", "active"],
    queryFn: () => listRosterBaseStations(),
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
        action: <Link className="portal-help-button portal-help-button--primary" to={`${root}/admin/amo-assets?section=operating-structure&returnTo=${returnTo}`}>Open operating structure</Link>,
      });
    }
    if (shiftsQuery.isSuccess && shiftsQuery.data.length === 0) {
      items.push({
        id: "shifts",
        title: "Create shift templates",
        detail: "Define reusable day, night, standby and off-duty windows before placing personnel on the roster.",
        action: <Link className="portal-help-button portal-help-button--primary" to={`${root}/rostering/settings?tab=shifts&returnTo=${returnTo}`}>Create shifts</Link>,
      });
    }
    if (periodsQuery.isSuccess && periodsQuery.data.length === 0) {
      items.push({
        id: "periods",
        title: "Create a planning period",
        detail: "The planner needs a dated period and a draft version before assignments can be created.",
        action: <Link className="portal-help-button portal-help-button--primary" to={`${root}/rostering/settings?tab=periods&returnTo=${returnTo}`}>Create period</Link>,
      });
    }
    return items;
  }, [basesQuery.data, basesQuery.isSuccess, periodsQuery.data, periodsQuery.isSuccess, returnTo, root, shiftsQuery.data, shiftsQuery.isSuccess]);

  const prerequisiteOpen = prerequisitesResolved && prerequisiteItems.length > 0 && !prerequisiteDismissed;

  return (
    <div style={{ display: "grid", gap: "0.5rem", minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "flex-end", minHeight: "2rem" }}>
        <PlannerCommitmentHelp autoOpen={prerequisitesResolved && prerequisiteItems.length === 0} settingsRoute={`${root}/rostering/settings`} />
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
        allowReadOnly={false}
        onClose={() => setPrerequisiteDismissed(true)}
      />
    </div>
  );
}
