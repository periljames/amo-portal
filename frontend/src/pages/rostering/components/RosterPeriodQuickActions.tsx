import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  Check,
  Clock3,
  FilePlus2,
  GitBranchPlus,
  Pencil,
  Plus,
  Save,
  X,
} from "lucide-react";

import {
  createRosterPeriod,
  createRosterVersion,
  listRosterPeriods,
  updateRosterPeriod,
} from "../../../services/rostering";
import type {
  RosterPeriodRead,
  RosterPeriodStatus,
  RosterAmendmentType,
} from "../../../types/rostering";
import { errorMessage, newIdempotencyKey } from "../rosterUi";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import { StatusPill } from "./RosterShell";

type PeriodDraft = {
  id: string | null;
  period_code: string;
  name: string;
  starts_on: string;
  ends_on: string;
  timezone_name: string;
  notes: string;
  status: RosterPeriodStatus;
};

type AmendmentDraft = {
  period: RosterPeriodRead;
  sourceVersionId: string;
  sourceVersionNo: number;
  amendmentType: RosterAmendmentType;
  reason: string;
};

type IntlTimeZoneSupport = typeof Intl & {
  supportedValuesOf?: (key: "timeZone") => string[];
};

const FALLBACK_TIMEZONES = [
  "UTC",
  "Africa/Nairobi",
  "Africa/Addis_Ababa",
  "Africa/Dar_es_Salaam",
  "Africa/Kampala",
  "Africa/Johannesburg",
  "Asia/Dubai",
  "Asia/Doha",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Europe/Amsterdam",
  "Europe/London",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/New_York",
  "Australia/Sydney",
];

function localIsoDate(value: Date): string {
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

function detectedTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function monthDraft(offset: number, timezoneName: string): PeriodDraft {
  const today = new Date();
  const starts = new Date(today.getFullYear(), today.getMonth() + offset, 1);
  const ends = new Date(today.getFullYear(), today.getMonth() + offset + 1, 0);
  const code = `${starts.getFullYear()}-${String(starts.getMonth() + 1).padStart(2, "0")}`;
  return {
    id: null,
    period_code: code,
    name: "Monthly duty roster",
    starts_on: localIsoDate(starts),
    ends_on: localIsoDate(ends),
    timezone_name: timezoneName,
    notes: "",
    status: "DRAFT",
  };
}

function editDraft(period: RosterPeriodRead): PeriodDraft {
  return {
    id: period.id,
    period_code: period.period_code,
    name: period.name,
    starts_on: period.starts_on,
    ends_on: period.ends_on,
    timezone_name: period.timezone_name,
    notes: period.notes || "",
    status: period.status,
  };
}

function readableRange(period: Pick<RosterPeriodRead, "starts_on" | "ends_on">): string {
  const formatter = new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const start = new Date(`${period.starts_on}T12:00:00`);
  const end = new Date(`${period.ends_on}T12:00:00`);
  return `${formatter.format(start)} – ${formatter.format(end)}`;
}

export function RosterPeriodQuickActions() {
  const queryClient = useQueryClient();
  const browserTimeZone = useMemo(detectedTimeZone, []);
  const [draft, setDraft] = useState<PeriodDraft | null>(null);
  const [amendment, setAmendment] = useState<AmendmentDraft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const periodsQuery = useQuery({
    queryKey: ["rostering", "settings", "periods"],
    queryFn: () => listRosterPeriods(),
    staleTime: 2 * 60_000,
    networkMode: "offlineFirst",
  });
  const permissionsQuery = useWorkforcePermissions();

  const periods = useMemo(
    () => [...(periodsQuery.data || [])].sort((left, right) => right.starts_on.localeCompare(left.starts_on)),
    [periodsQuery.data],
  );
  const permissions = permissionsQuery.data?.permissions || [];
  const canCreate = permissions.includes("roster.create");
  const canEdit = permissions.includes("roster.edit");

  const timezoneOptions = useMemo(() => {
    let supported: string[] = [];
    try {
      supported = (Intl as IntlTimeZoneSupport).supportedValuesOf?.("timeZone") || [];
    } catch {
      supported = [];
    }
    return [...new Set([
      browserTimeZone,
      ...periods.map((period) => period.timezone_name),
      ...(supported.length ? supported : FALLBACK_TIMEZONES),
    ].filter(Boolean))].sort((left, right) => left.localeCompare(right));
  }, [browserTimeZone, periods]);

  const today = localIsoDate(new Date());
  const currentPeriod = periods.find((period) => period.starts_on <= today && period.ends_on >= today) || periods[0];
  const recentPeriods = periods.slice(0, 4);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["rostering"] });
  };

  const save = async () => {
    if (!draft) return;
    if (!draft.period_code.trim() || !draft.name.trim()) {
      setError("Period code and name are required.");
      return;
    }
    if (!draft.starts_on || !draft.ends_on || draft.ends_on < draft.starts_on) {
      setError("The period end date must be on or after the start date.");
      return;
    }
    if (!draft.timezone_name) {
      setError("Select the timezone used for roster dates and shift boundaries.");
      return;
    }
    const overlap = periods.find((period) => (
      period.id !== draft.id
      && period.status !== "ARCHIVED"
      && period.starts_on <= draft.ends_on
      && period.ends_on >= draft.starts_on
    ));
    if (!draft.id && overlap) {
      setError(`This date range overlaps ${overlap.period_code} (${overlap.starts_on} to ${overlap.ends_on}). Archive or adjust the existing period first.`);
      return;
    }

    setBusy(draft.id ? `edit:${draft.id}` : "create");
    setError(null);
    try {
      if (draft.id) {
        await updateRosterPeriod(draft.id, {
          name: draft.name.trim(),
          timezone_name: draft.timezone_name,
          notes: draft.notes.trim() || null,
          status: draft.status,
        });
      } else {
        await createRosterPeriod({
          period_code: draft.period_code.trim().toUpperCase(),
          name: draft.name.trim(),
          starts_on: draft.starts_on,
          ends_on: draft.ends_on,
          timezone_name: draft.timezone_name,
          notes: draft.notes.trim() || null,
        });
      }
      setDraft(null);
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const createDraftVersion = async (period: RosterPeriodRead) => {
    setBusy(`version:${period.id}`);
    setError(null);
    try {
      await createRosterVersion(period.id, {
        title: `Draft v${period.versions.length + 1}`,
        idempotency_key: newIdempotencyKey("version"),
      });
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const beginAmendment = (period: RosterPeriodRead) => {
    const source = [...period.versions]
      .filter((version) => version.status === "PUBLISHED")
      .sort((left, right) => right.version_no - left.version_no)[0];
    if (!source) {
      void createDraftVersion(period);
      return;
    }
    setError(null);
    setAmendment({
      period,
      sourceVersionId: source.id,
      sourceVersionNo: source.version_no,
      amendmentType: "LEAVE",
      reason: "",
    });
  };

  const createAmendment = async () => {
    if (!amendment) return;
    if (amendment.reason.trim().length < 5) {
      setError("Enter an audited reason for the published-roster amendment.");
      return;
    }
    setBusy(`amend:${amendment.period.id}`);
    setError(null);
    try {
      await createRosterVersion(amendment.period.id, {
        title: `Amendment of v${amendment.sourceVersionNo}`,
        copy_from_version_id: amendment.sourceVersionId,
        amendment_type: amendment.amendmentType,
        amendment_reason: amendment.reason.trim(),
        change_summary: `Controlled ${amendment.amendmentType.toLowerCase()} amendment`,
        idempotency_key: newIdempotencyKey("amendment"),
      });
      setAmendment(null);
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="wr-panel wr-period-quick" aria-labelledby="period-quick-title">
      <div className="wr-period-quick__header">
        <div>
          <span className="wr-eyebrow">Period control</span>
          <h2 id="period-quick-title">Roster periods</h2>
        </div>
        <div className="wr-period-quick__actions">
          {canCreate ? (
            <>
              <button type="button" className="wr-button wr-button--small" onClick={() => setDraft(monthDraft(0, browserTimeZone))}>
                <CalendarPlus size={15} /> This month
              </button>
              <button type="button" className="wr-button wr-button--primary" onClick={() => setDraft(monthDraft(1, browserTimeZone))}>
                <Plus size={16} /> New period
              </button>
            </>
          ) : null}
        </div>
      </div>

      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}
      {periodsQuery.error ? <div className="wr-inline-error" role="alert">{errorMessage(periodsQuery.error)}</div> : null}

      {currentPeriod ? (
        <div className="wr-period-current">
          <div className="wr-period-current__icon"><Clock3 size={18} /></div>
          <div>
            <strong>{currentPeriod.period_code} · {currentPeriod.name}</strong>
            <span>{readableRange(currentPeriod)} · {currentPeriod.timezone_name}</span>
          </div>
          <StatusPill value={currentPeriod.status} />
          <span>{currentPeriod.versions.length} version{currentPeriod.versions.length === 1 ? "" : "s"}</span>
        </div>
      ) : (
        <div className="wr-period-current is-empty">
          <div className="wr-period-current__icon"><CalendarPlus size={18} /></div>
          <div><strong>No roster period</strong><span>Create one before opening a planning draft.</span></div>
        </div>
      )}

      {draft ? (
        <div className="wr-period-editor">
          <div className="wr-period-editor__heading">
            <strong>{draft.id ? "Edit period" : "Create period"}</strong>
            <button type="button" className="wr-icon-button" aria-label="Close period editor" onClick={() => { setDraft(null); setError(null); }}><X size={16} /></button>
          </div>
          <div className="wr-period-editor__grid">
            <label><span>Code</span><input value={draft.period_code} onChange={(event) => setDraft({ ...draft, period_code: event.target.value })} /></label>
            <label><span>Name</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
            <label><span>Starts</span><input type="date" value={draft.starts_on} disabled={Boolean(draft.id)} onChange={(event) => setDraft({ ...draft, starts_on: event.target.value })} />{draft.id ? <small>Dates are locked after creation to preserve version history.</small> : null}</label>
            <label><span>Ends</span><input type="date" value={draft.ends_on} disabled={Boolean(draft.id)} onChange={(event) => setDraft({ ...draft, ends_on: event.target.value })} /></label>
            <label className="wr-period-editor__timezone">
              <span>Timezone</span>
              <select value={draft.timezone_name} onChange={(event) => setDraft({ ...draft, timezone_name: event.target.value })}>
                {timezoneOptions.map((timezone) => (
                  <option key={timezone} value={timezone}>{timezone}{timezone === browserTimeZone ? " · detected" : ""}</option>
                ))}
              </select>
              <small>Detected from this browser: {browserTimeZone}</small>
            </label>
            {draft.id ? (
              <label><span>Status</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as RosterPeriodStatus })}>{["DRAFT", "OPEN", "LOCKED", "ARCHIVED"].map((value) => <option key={value}>{value}</option>)}</select></label>
            ) : null}
            <label className="wr-period-editor__notes"><span>Notes</span><input value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} placeholder="Optional planning note" /></label>
          </div>
          <div className="wr-actions wr-actions--end">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => setDraft(null)}>Cancel</button>
            <button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy)} onClick={() => void save()}><Save size={15} /> Save period</button>
          </div>
        </div>
      ) : null}

      {amendment ? (
        <div className="wr-period-editor" role="dialog" aria-modal="true" aria-label={`Amend ${amendment.period.period_code}`}>
          <div className="wr-period-editor__heading">
            <div><span className="wr-eyebrow">Published roster control</span><strong>Amend {amendment.period.period_code} from v{amendment.sourceVersionNo}</strong></div>
            <button type="button" className="wr-icon-button" aria-label="Close amendment form" onClick={() => { setAmendment(null); setError(null); }}><X size={16} /></button>
          </div>
          <p className="wr-period-editor__guidance">The full published duty set, open task links and aircraft allocations will be copied into a new draft. Approved leave and scheduled classes remain protected so the planner can apply a ranked rotation.</p>
          <div className="wr-period-editor__grid">
            <label><span>Amendment type</span><select value={amendment.amendmentType} onChange={(event) => setAmendment({ ...amendment, amendmentType: event.target.value as RosterAmendmentType })}>{["LEAVE", "SICKNESS", "TRAINING", "COVERAGE", "OPERATIONAL", "CORRECTION", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label className="wr-period-editor__notes"><span>Audited reason</span><input value={amendment.reason} onChange={(event) => setAmendment({ ...amendment, reason: event.target.value })} placeholder="For example: approved annual leave for scheduled engineer" /></label>
          </div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setAmendment(null)}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={Boolean(busy) || amendment.reason.trim().length < 5} onClick={() => void createAmendment()}><GitBranchPlus size={15} /> Create amendment draft</button></div>
        </div>
      ) : null}

      {recentPeriods.length ? (
        <div className="wr-period-quick__list">
          {recentPeriods.map((period) => (
            <article key={period.id} className="wr-period-quick__row">
              <div>
                <strong>{period.period_code}</strong>
                <span>{period.name}</span>
                <small>{readableRange(period)} · {period.timezone_name}</small>
              </div>
              <StatusPill value={period.status} />
              <div className="wr-actions">
                {canEdit ? <button type="button" className="wr-button wr-button--small" onClick={() => setDraft(editDraft(period))}><Pencil size={14} /> Edit</button> : null}
                {canCreate ? <button type="button" className="wr-button wr-button--small" disabled={Boolean(busy)} onClick={() => beginAmendment(period)}>{period.versions.some((version) => version.status === "PUBLISHED") ? <GitBranchPlus size={14} /> : <FilePlus2 size={14} />} {period.versions.some((version) => version.status === "PUBLISHED") ? "Amend" : "Draft"}</button> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      {!permissionsQuery.isPending && !canCreate && !canEdit ? (
        <div className="wr-period-quick__readonly"><Check size={15} /> Periods are managed by authorised roster planners.</div>
      ) : null}
    </section>
  );
}
