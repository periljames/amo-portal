import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, Plane, Plus, Save, Settings2, ShieldCheck, Tags, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import {
  createRosterLegacyAlias,
  deleteRosterLegacyAlias,
  deleteUnusedRosterCode,
  installRecommendedRosterCodes,
  listRosterCodeRegistry,
  listRosterLegacyAliases,
  updateRosterCodePolicy,
  type RosterCalendarMode,
  type RosterCodeRegistryEntry,
  type RosterCodeVerificationStatus,
  type RosterDutySemantic,
} from "../../../services/rosteringCodeRegistry";
import { errorMessage } from "../rosterUi";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import { RosterLoading, StatusPill } from "./RosterShell";

const REGISTRY_KEY = ["rostering", "settings", "code-registry"] as const;
const ALIASES_KEY = ["rostering", "settings", "code-aliases"] as const;
const MODES: RosterCalendarMode[] = ["TIMED", "ALL_DAY", "HIDDEN"];
const SEMANTICS: RosterDutySemantic[] = ["DUTY", "STANDBY", "TRAINING", "REST", "OFF", "LEAVE", "SICK", "OTHER"];
const VERIFICATION: RosterCodeVerificationStatus[] = ["CONFIRMED", "REVIEW_REQUIRED", "UNRESOLVED"];

function timeLabel(row: RosterCodeRegistryEntry): string {
  if (!row.default_start_time || !row.default_end_time) return "Assignment times";
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
  onSave: (
    row: RosterCodeRegistryEntry,
    values: {
      unpaid_break_minutes: number;
      calendar_mode: RosterCalendarMode;
      duty_semantic: RosterDutySemantic;
      verification_status: RosterCodeVerificationStatus;
      source_reference: string | null;
    },
  ) => Promise<void>;
  onDelete: (row: RosterCodeRegistryEntry) => Promise<void>;
}) {
  const [breakMinutes, setBreakMinutes] = useState(row.policy.unpaid_break_minutes);
  const [calendarMode, setCalendarMode] = useState<RosterCalendarMode>(row.policy.calendar_mode);
  const [semantic, setSemantic] = useState<RosterDutySemantic>(row.policy.duty_semantic);
  const [verification, setVerification] = useState<RosterCodeVerificationStatus>(row.policy.verification_status);
  const [sourceReference, setSourceReference] = useState(row.policy.source_reference || "");

  useEffect(() => {
    setBreakMinutes(row.policy.unpaid_break_minutes);
    setCalendarMode(row.policy.calendar_mode);
    setSemantic(row.policy.duty_semantic);
    setVerification(row.policy.verification_status);
    setSourceReference(row.policy.source_reference || "");
  }, [row.policy]);

  const changed = breakMinutes !== row.policy.unpaid_break_minutes
    || calendarMode !== row.policy.calendar_mode
    || semantic !== row.policy.duty_semantic
    || verification !== row.policy.verification_status
    || sourceReference !== (row.policy.source_reference || "");

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
          style={{ width: 78 }}
        />
      </td>
      <td>
        <select aria-label={`${row.code} semantic`} value={semantic} disabled={!canManage} onChange={(event) => setSemantic(event.target.value as RosterDutySemantic)}>
          {SEMANTICS.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
        </select>
      </td>
      <td>
        <select aria-label={`${row.code} calendar mode`} value={calendarMode} disabled={!canManage} onChange={(event) => setCalendarMode(event.target.value as RosterCalendarMode)}>
          {MODES.map((mode) => <option key={mode} value={mode}>{mode.replace("_", " ")}</option>)}
        </select>
      </td>
      <td>
        <select aria-label={`${row.code} verification`} value={verification} disabled={!canManage} onChange={(event) => setVerification(event.target.value as RosterCodeVerificationStatus)}>
          {VERIFICATION.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
        </select>
        <input
          aria-label={`${row.code} source reference`}
          placeholder="Source / evidence reference"
          value={sourceReference}
          disabled={!canManage}
          onChange={(event) => setSourceReference(event.target.value)}
          style={{ minWidth: 190, marginTop: 6 }}
        />
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
              onClick={() => void onSave(row, {
                unpaid_break_minutes: breakMinutes,
                calendar_mode: calendarMode,
                duty_semantic: semantic,
                verification_status: verification,
                source_reference: sourceReference.trim() || null,
              })}
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
  const [aliasTemplateId, setAliasTemplateId] = useState("");
  const [aliasCode, setAliasCode] = useState("");
  const [aliasContext, setAliasContext] = useState("");
  const [aliasAircraft, setAliasAircraft] = useState("");
  const registryQuery = useQuery({ queryKey: REGISTRY_KEY, queryFn: listRosterCodeRegistry, staleTime: 5 * 60_000 });
  const aliasesQuery = useQuery({ queryKey: ALIASES_KEY, queryFn: () => listRosterLegacyAliases(), staleTime: 5 * 60_000 });
  const permissionsQuery = useWorkforcePermissions();
  const rows = registryQuery.data || [];
  const aliases = aliasesQuery.data || [];
  const canManage = (permissionsQuery.data?.permissions || []).includes("roster.manage_shift_templates");
  const templateById = useMemo(() => new Map(rows.map((row) => [row.id, row])), [rows]);
  const effectiveAliasTemplateId = aliasTemplateId || rows[0]?.id || "";

  const refresh = async () => {
    await Promise.allSettled([
      queryClient.invalidateQueries({ queryKey: ["rostering"] }),
      registryQuery.refetch(),
      aliasesQuery.refetch(),
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
    values: {
      unpaid_break_minutes: number;
      calendar_mode: RosterCalendarMode;
      duty_semantic: RosterDutySemantic;
      verification_status: RosterCodeVerificationStatus;
      source_reference: string | null;
    },
  ) => {
    setBusy(`save:${row.id}`);
    setActionError(null);
    try {
      await updateRosterCodePolicy(row.id, values);
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

  const addAlias = async () => {
    if (!effectiveAliasTemplateId || !aliasCode.trim()) return;
    setBusy("alias:add");
    setActionError(null);
    try {
      await createRosterLegacyAlias(effectiveAliasTemplateId, {
        alias: aliasCode,
        context_label: aliasContext.trim() || null,
        aircraft_registration: aliasAircraft.trim() || null,
      });
      setAliasCode("");
      setAliasContext("");
      setAliasAircraft("");
      await refresh();
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const removeAlias = async (aliasId: string) => {
    setBusy(`alias:${aliasId}`);
    setActionError(null);
    try {
      await deleteRosterLegacyAlias(aliasId);
      await refresh();
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  if (registryQuery.isPending && !registryQuery.data) return <RosterLoading label="Loading roster code registry…" />;

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Advanced controls</span>
          <h2>Code policy</h2>
          <p>Review imported aliases and publication semantics.</p>
        </div>
        <span className="wr-header-badge"><Settings2 size={15} /> 1–2 characters required</span>
      </div>

      {actionError ? <div className="wr-inline-error" role="alert">{actionError}</div> : null}
      {registryQuery.error || aliasesQuery.error ? <div className="wr-inline-error" role="alert">{errorMessage(registryQuery.error || aliasesQuery.error)}</div> : null}

      {rows.length === 0 ? (
        <div className="wr-two-column">
          <article className="wr-panel">
            <ShieldCheck size={20} />
            <h3>Recommended AMO starter pack</h3>
            <p>Install DY, AM, PM, XD, WD, NT, F1, F2, FD, SB, TR, OF and RD. Starter codes are installed as confirmed tenant-owned records and are never silently re-created after deletion.</p>
            {canManage ? <button type="button" className="wr-button wr-button--primary" disabled={busy === "starter"} onClick={() => void install()}><Plus size={15} /> Use recommended AMO codes</button> : null}
          </article>
          <article className="wr-panel">
            <Clock3 size={20} />
            <h3>Start blank</h3>
            <p>Keep the library empty and create tenant-specific codes manually. New codes remain unresolved until their semantic and source are reviewed here.</p>
            <Link className="wr-button wr-button--secondary" to="?section=patterns">Open shift types</Link>
          </article>
        </div>
      ) : (
        <>
          <div className="wr-inline-warning" role="status"><Plane size={16} /> Aircraft such as 5Y-SLC are allocated to the duty assignment; they are not shift codes. JKIA remains a base station. Unresolved or review-required codes block publication.</div>
          <div className="wr-table-wrap">
            <table className="wr-table">
              <thead><tr><th>Code</th><th>Type</th><th>Default time</th><th>Break</th><th>Semantic</th><th>Calendar</th><th>Verification / source</th><th>Uses</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>{rows.map((row) => <PolicyRow key={row.id} row={row} canManage={canManage} busy={busy} onSave={savePolicy} onDelete={remove} />)}</tbody>
            </table>
          </div>

          <section className="wr-panel" style={{ marginTop: 16 }}>
            <div className="wr-section-heading">
              <div><span className="wr-eyebrow">Legacy import mapping</span><h3><Tags size={17} /> Aliases</h3><p>Map historical spellings such as H.A or single-character legacy cells to one canonical code. Optional context and aircraft fields preserve facts that should not become shift codes.</p></div>
            </div>
            {canManage ? (
              <div className="wr-form-grid">
                <label>Canonical code<select value={effectiveAliasTemplateId} onChange={(event) => setAliasTemplateId(event.target.value)}>{rows.map((row) => <option key={row.id} value={row.id}>{row.code} — {row.label}</option>)}</select></label>
                <label>Legacy alias<input value={aliasCode} placeholder="e.g. H.A" onChange={(event) => setAliasCode(event.target.value)} /></label>
                <label>Context (optional)<input value={aliasContext} placeholder="e.g. Hangar" onChange={(event) => setAliasContext(event.target.value)} /></label>
                <label>Aircraft (optional)<input value={aliasAircraft} placeholder="e.g. 5Y-SLC" onChange={(event) => setAliasAircraft(event.target.value)} /></label>
                <div className="wr-actions"><button type="button" className="wr-button wr-button--primary" disabled={!aliasCode.trim() || busy === "alias:add"} onClick={() => void addAlias()}><Plus size={14} /> Add alias</button></div>
              </div>
            ) : null}
            {aliases.length ? (
              <div className="wr-table-wrap"><table className="wr-table"><thead><tr><th>Legacy</th><th>Canonical</th><th>Context</th><th>Aircraft</th><th /></tr></thead><tbody>{aliases.map((alias) => <tr key={alias.id}><td><strong>{alias.alias}</strong></td><td>{templateById.get(alias.shift_template_id)?.code || alias.shift_template_id}</td><td>{alias.context_label || "—"}</td><td>{alias.aircraft_registration || "—"}</td><td>{canManage ? <button type="button" className="wr-button wr-button--small" disabled={busy === `alias:${alias.id}`} onClick={() => void removeAlias(alias.id)}><Trash2 size={13} /> Remove</button> : null}</td></tr>)}</tbody></table></div>
            ) : <p className="wr-muted">No legacy aliases configured.</p>}
          </section>

          <div className="wr-actions wr-actions--end">
            <Link className="wr-button wr-button--secondary" to="?section=patterns"><Settings2 size={15} /> Edit shift types</Link>
            {canManage ? <button type="button" className="wr-button wr-button--secondary" disabled={busy === "starter"} onClick={() => void install()}><Plus size={15} /> Add missing recommended codes</button> : null}
          </div>
        </>
      )}
    </section>
  );
}
