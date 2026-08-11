import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, Plane, Plus, Save, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { getCurrentWorkforcePermissions } from "../../../services/workforce";
import {
  deleteUnusedRosterCode,
  installRecommendedRosterCodes,
  listRosterCodeRegistry,
  updateRosterCodePolicy,
  type RosterCalendarMode,
  type RosterCodeRegistryEntry,
} from "../../../services/rosteringCodeRegistry";
import { errorMessage } from "../rosterUi";
import { RosterLoading, StatusPill } from "./RosterShell";

const REGISTRY_KEY = ["rostering", "settings", "code-registry"] as const;
const MODES: RosterCalendarMode[] = ["TIMED", "ALL_DAY", "HIDDEN"];

function timeLabel(row: RosterCodeRegistryEntry): string {
  if (!row.default_start_time || !row.default_end_time) return "Tenant configured";
  return `${row.default_start_time}–${row.default_end_time}`;
}

function PolicyRow({
  row,
  canManage,
  busy,
  onSave,
  onDelete,
}: {
  row: RosterCodeRegistryEntry;
  canManage: boolean;
  busy: string | null;
  onSave: (row: RosterCodeRegistryEntry, breakMinutes: number, calendarMode: RosterCalendarMode) => Promise<void>;
  onDelete: (row: RosterCodeRegistryEntry) => Promise<void>;
}) {
  const [breakMinutes, setBreakMinutes] = useState(row.policy.unpaid_break_minutes);
  const [calendarMode, setCalendarMode] = useState<RosterCalendarMode>(row.policy.calendar_mode);

  useEffect(() => {
    setBreakMinutes(row.policy.unpaid_break_minutes);
    setCalendarMode(row.policy.calendar_mode);
  }, [row.policy.calendar_mode, row.policy.unpaid_break_minutes]);

  const changed = breakMinutes !== row.policy.unpaid_break_minutes || calendarMode !== row.policy.calendar_mode;

  return (
    <tr>
      <td><strong>{row.code}</strong><small>{row.label}</small></td>
      <td><StatusPill value={row.kind} /></td>
      <td>{timeLabel(row)}</td>
      <td>
        <input
          aria-label={`${row.code} unpaid break minutes`}
          type="number"
          min="0"
          max="1440"
          value={breakMinutes}
          disabled={!canManage}
          onChange={(event) => setBreakMinutes(Number(event.target.value))}
          style={{ width: 88 }}
        />
      </td>
      <td>
        <select
          aria-label={`${row.code} calendar mode`}
          value={calendarMode}
          disabled={!canManage}
          onChange={(event) => setCalendarMode(event.target.value as RosterCalendarMode)}
        >
          {MODES.map((mode) => <option key={mode} value={mode}>{mode.replace("_", " ")}</option>)}
        </select>
      </td>
      <td>{row.usage_count}</td>
      <td><StatusPill value={row.is_active ? "ACTIVE" : "INACTIVE"} /></td>
      <td>
        {canManage ? (
          <div className="wr-actions">
            <button
              type="button"
              className="wr-button wr-button--small"
              disabled={!changed || busy === `save:${row.id}`}
              onClick={() => void onSave(row, breakMinutes, calendarMode)}
            >
              <Save size={13} /> Save
            </button>
            <button
              type="button"
              className="wr-button wr-button--small"
              disabled={!row.can_delete || busy === `delete:${row.id}`}
              title={row.can_delete ? "Delete unused code" : "Used codes must be retired, not deleted"}
              onClick={() => void onDelete(row)}
            >
              <Trash2 size={13} /> Delete
            </button>
          </div>
        ) : null}
      </td>
    </tr>
  );
}

export function RosterCodeRegistryPanel() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const registryQuery = useQuery({
    queryKey: REGISTRY_KEY,
    queryFn: listRosterCodeRegistry,
    staleTime: 5 * 60_000,
  });
  const permissionsQuery = useQuery({
    queryKey: ["rostering", "settings", "permissions"],
    queryFn: getCurrentWorkforcePermissions,
    staleTime: 15 * 60_000,
  });
  const rows = registryQuery.data || [];
  const canManage = (permissionsQuery.data?.permissions || []).includes("roster.manage_shift_templates");

  const refresh = async () => {
    await Promise.allSettled([
      queryClient.invalidateQueries({ queryKey: ["rostering"] }),
      registryQuery.refetch(),
    ]);
  };

  const install = async () => {
    setBusy("starter");
    setActionError(null);
    try {
      await installRecommendedRosterCodes();
      await refresh();
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const savePolicy = async (
    row: RosterCodeRegistryEntry,
    unpaidBreakMinutes: number,
    calendarMode: RosterCalendarMode,
  ) => {
    setBusy(`save:${row.id}`);
    setActionError(null);
    try {
      await updateRosterCodePolicy(row.id, {
        unpaid_break_minutes: unpaidBreakMinutes,
        calendar_mode: calendarMode,
      });
      await refresh();
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (row: RosterCodeRegistryEntry) => {
    if (!window.confirm(`Delete unused roster code ${row.code}?`)) return;
    setBusy(`delete:${row.id}`);
    setActionError(null);
    try {
      await deleteUnusedRosterCode(row.id);
      await refresh();
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  if (registryQuery.isPending && !registryQuery.data) {
    return <RosterLoading label="Loading roster code registry…" />;
  }

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Tenant roster vocabulary</span>
          <h2>Roster code registry</h2>
          <p>Shift codes describe when a person works. Base stations, departments/work centres and aircraft allocations stay separate.</p>
        </div>
        <span className="wr-header-badge"><Settings2 size={15} /> 2-character codes recommended</span>
      </div>

      {actionError ? <div className="wr-inline-error" role="alert">{actionError}</div> : null}
      {registryQuery.error ? <div className="wr-inline-error" role="alert">{errorMessage(registryQuery.error)}</div> : null}

      {rows.length === 0 ? (
        <div className="wr-two-column">
          <article className="wr-panel">
            <ShieldCheck size={20} />
            <h3>Recommended AMO starter pack</h3>
            <p>Install DY, AM, PM, XD, WD, NT, F1, F2, FD, SB, TR, OF and RD. The records become tenant-owned and are never silently re-created after deletion.</p>
            {canManage ? (
              <button type="button" className="wr-button wr-button--primary" disabled={busy === "starter"} onClick={() => void install()}>
                <Plus size={15} /> Use recommended AMO codes
              </button>
            ) : null}
          </article>
          <article className="wr-panel">
            <Clock3 size={20} />
            <h3>Start blank</h3>
            <p>Keep the library empty and create tenant-specific codes manually. Canonical codes accept 2–8 uppercase letters/numbers; punctuation such as H.A is rejected.</p>
            <Link className="wr-button wr-button--secondary" to="?section=shifts">Open shift library</Link>
          </article>
        </div>
      ) : (
        <>
          <div className="wr-inline-warning" role="status">
            <Plane size={16} /> Aircraft such as 5Y-SLC are allocated to the duty assignment; they are not shift codes. JKIA remains a base station.
          </div>
          <div className="wr-table-wrap">
            <table className="wr-table">
              <thead>
                <tr><th>Code</th><th>Type</th><th>Default time</th><th>Unpaid break</th><th>Calendar</th><th>Uses</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <PolicyRow key={row.id} row={row} canManage={canManage} busy={busy} onSave={savePolicy} onDelete={remove} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="wr-actions wr-actions--end">
            <Link className="wr-button wr-button--secondary" to="?section=shifts"><Settings2 size={15} /> Edit shift times and labels</Link>
            {canManage ? (
              <button type="button" className="wr-button wr-button--secondary" disabled={busy === "starter"} onClick={() => void install()}>
                <Plus size={15} /> Add missing recommended codes
              </button>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
