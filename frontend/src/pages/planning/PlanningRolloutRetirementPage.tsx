import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import { listMigrationBatches, type MigrationBatch } from "../../services/migrationControl";
import { listFleetAircraft, type FleetAircraft } from "../../services/production";
import {
  assessRolloutWave,
  createRolloutGroup,
  createRolloutWave,
  createSpreadsheetRegisterItem,
  getRolloutDashboard,
  listRolloutGroups,
  listSpreadsheetRegister,
  transitionRolloutAircraft,
  transitionRolloutWave,
  transitionSpreadsheet,
  updateRolloutChecklist,
  type RolloutAircraft,
  type RolloutDashboard,
  type RolloutGroup,
  type RolloutWave,
  type SpreadsheetRegisterItem,
} from "../../services/rolloutControl";
import { formatCapabilitiesForUi } from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/planning-phase2.css";
import "../../styles/rollout-retirement.css";

const emptyDashboard: RolloutDashboard = {
  groups: 0,
  waves: 0,
  active_waves: 0,
  aircraft_planned: 0,
  aircraft_dual_run: 0,
  aircraft_cutover: 0,
  aircraft_verified: 0,
  aircraft_complete: 0,
  aircraft_hold: 0,
  spreadsheet_live: 0,
  spreadsheet_dual_run: 0,
  spreadsheet_read_only: 0,
  spreadsheet_retired: 0,
  spreadsheet_archived: 0,
};

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(parsed);
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const className = normalized.includes("hold") || normalized.includes("blocked") || normalized.includes("live")
    ? "badge badge--danger"
    : normalized.includes("planned") || normalized.includes("dual") || normalized.includes("cutover") || normalized.includes("read only") || normalized.includes("read_only")
      ? "badge badge--warning"
      : normalized.includes("complete") || normalized.includes("verified") || normalized.includes("ready") || normalized.includes("retired") || normalized.includes("archived")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

const nextAircraftAction: Record<RolloutAircraft["status"], RolloutAircraft["status"] | null> = {
  PLANNED: "DUAL_RUN",
  DUAL_RUN: "CUTOVER",
  CUTOVER: "VERIFIED",
  VERIFIED: "COMPLETE",
  COMPLETE: null,
  HOLD: "PLANNED",
};

const nextWaveAction: Record<string, string | null> = {
  PLANNED: "READY",
  READY: "IN_PROGRESS",
  IN_PROGRESS: "COMPLETE",
  HOLD: "PLANNED",
  COMPLETE: null,
  CANCELLED: null,
};

const nextSpreadsheetAction: Record<SpreadsheetRegisterItem["status"], SpreadsheetRegisterItem["status"] | null> = {
  LIVE: "DUAL_RUN",
  DUAL_RUN: "READ_ONLY",
  READ_ONLY: "RETIRED",
  RETIRED: "ARCHIVED",
  ARCHIVED: null,
};

export const PlanningRolloutRetirementPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const [dashboard, setDashboard] = useState<RolloutDashboard>(emptyDashboard);
  const [groups, setGroups] = useState<RolloutGroup[]>([]);
  const [aircraft, setAircraft] = useState<FleetAircraft[]>([]);
  const [migrationBatches, setMigrationBatches] = useState<MigrationBatch[]>([]);
  const [spreadsheets, setSpreadsheets] = useState<SpreadsheetRegisterItem[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [selectedWaveId, setSelectedWaveId] = useState("");
  const [selectedAircraft, setSelectedAircraft] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [groupDraft, setGroupDraft] = useState({ name: "Fleet rollout", description: "Controlled aircraft migration and cutover programme." });
  const [waveDraft, setWaveDraft] = useState({ name: "Wave 1", sequence_no: 1, planned_start: "", planned_end: "" });
  const [sheetDraft, setSheetDraft] = useState({
    name: "",
    owner: "",
    location: "",
    purpose: "",
    data_domain: "UTILISATION",
    replacement_route: `/maintenance/${amoCode}/planning/utilisation-monitoring`,
    criteria: "Dual-run reconciled\nUsers trained\nPortal evidence approved\nRollback period completed",
  });

  const reload = useCallback(async () => {
    const [dashboardData, groupRows, fleetRows, migrationRows, spreadsheetRows] = await Promise.all([
      getRolloutDashboard(),
      listRolloutGroups(),
      listFleetAircraft(),
      listMigrationBatches(),
      listSpreadsheetRegister(),
    ]);
    setDashboard(dashboardData);
    setGroups(groupRows);
    setAircraft(fleetRows);
    setMigrationBatches(migrationRows);
    setSpreadsheets(spreadsheetRows);
    setSelectedGroupId((current) => current || groupRows[0]?.id || "");
    setSelectedWaveId((current) => current || groupRows[0]?.waves[0]?.id || "");
  }, []);

  useEffect(() => {
    void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Rollout control could not be loaded."));
  }, [reload]);

  const selectedGroup = useMemo(() => groups.find((row) => row.id === selectedGroupId) || groups[0] || null, [groups, selectedGroupId]);
  const allWaves = useMemo(() => groups.flatMap((group) => group.waves), [groups]);
  const selectedWave = useMemo(() => allWaves.find((row) => row.id === selectedWaveId) || selectedGroup?.waves[0] || allWaves[0] || null, [allWaves, selectedGroup, selectedWaveId]);
  const committedBatches = useMemo(() => migrationBatches.filter((row) => row.status === "COMMITTED"), [migrationBatches]);

  const execute = async (success: string, action: () => Promise<unknown>) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Rollout operation failed.");
    } finally {
      setBusy(false);
    }
  };

  const createGroup = () => execute("Rollout group created.", async () => {
    const row = await createRolloutGroup({ ...groupDraft, selection_json: {} });
    setSelectedGroupId(row.id);
  });

  const createWave = () => execute("Rollout wave and controlled checklists created.", async () => {
    if (!selectedGroup) throw new Error("Create or select a rollout group first.");
    if (!selectedAircraft.length) throw new Error("Select at least one aircraft for the wave.");
    const row = await createRolloutWave(selectedGroup.id, {
      ...waveDraft,
      planned_start: waveDraft.planned_start || undefined,
      planned_end: waveDraft.planned_end || undefined,
      aircraft_serial_numbers: selectedAircraft,
    });
    setSelectedWaveId(row.id);
    setSelectedAircraft([]);
  });

  const assessWave = () => execute("Wave readiness recalculated from live portal evidence.", async () => {
    if (!selectedWave) throw new Error("Select a rollout wave.");
    await assessRolloutWave(selectedWave.id);
  });

  const advanceWave = () => execute("Wave lifecycle advanced.", async () => {
    if (!selectedWave) return;
    const target = nextWaveAction[selectedWave.status];
    if (!target) throw new Error("The selected wave has no further transition.");
    const notes = window.prompt("Wave decision notes", `${selectedWave.name} approved for ${humanize(target)}.`);
    if (!notes?.trim()) throw new Error("Decision notes are required.");
    await transitionRolloutWave(selectedWave.id, target, notes.trim());
  });

  const setWaveHold = () => execute("Wave placed on hold.", async () => {
    if (!selectedWave) return;
    const notes = window.prompt("Hold reason");
    if (!notes?.trim()) throw new Error("Hold reason is required.");
    await transitionRolloutWave(selectedWave.id, "HOLD", notes.trim());
  });

  const advanceAircraft = (row: RolloutAircraft) => execute(`${row.registration} rollout state advanced.`, async () => {
    const target = nextAircraftAction[row.status];
    if (!target) throw new Error("This aircraft rollout is complete.");
    const migration = committedBatches.find((batch) => batch.target_aircraft_serial_number === row.aircraft_serial_number || batch.target_registration === row.registration);
    const notes = window.prompt("Aircraft transition notes", `${row.registration} moved to ${humanize(target)} after evidence review.`);
    if (!notes?.trim()) throw new Error("Transition notes are required.");
    await transitionRolloutAircraft(row.id, target, notes.trim(), migration?.id);
  });

  const holdAircraft = (row: RolloutAircraft) => execute(`${row.registration} placed on hold.`, async () => {
    const reason = window.prompt("Aircraft hold reason");
    if (!reason?.trim()) throw new Error("Hold reason is required.");
    await transitionRolloutAircraft(row.id, "HOLD", reason.trim(), row.migration_batch_id || undefined);
  });

  const toggleChecklist = (checklistId: string, current: string) => execute("Checklist evidence updated.", async () => {
    const next = current === "COMPLETE" ? "PENDING" : "COMPLETE";
    const notes = window.prompt("Checklist evidence notes", next === "COMPLETE" ? "Verified against portal and source evidence." : "Reopened for verification.");
    await updateRolloutChecklist(checklistId, next as "PENDING" | "COMPLETE", notes || undefined, []);
  });

  const registerSpreadsheet = () => execute("Spreadsheet added to the controlled retirement register.", async () => {
    if (!sheetDraft.name.trim() || !sheetDraft.purpose.trim()) throw new Error("Spreadsheet name and purpose are required.");
    await createSpreadsheetRegisterItem({
      name: sheetDraft.name.trim(),
      owner: sheetDraft.owner || undefined,
      location: sheetDraft.location || undefined,
      purpose: sheetDraft.purpose.trim(),
      data_domain: sheetDraft.data_domain,
      replacement_route: sheetDraft.replacement_route || undefined,
      retirement_criteria_json: sheetDraft.criteria.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    });
    setSheetDraft((current) => ({ ...current, name: "", location: "", purpose: "" }));
  });

  const advanceSpreadsheet = (row: SpreadsheetRegisterItem) => execute(`${row.name} moved to its next controlled state.`, async () => {
    const target = nextSpreadsheetAction[row.status];
    if (!target) throw new Error("Spreadsheet is already archived.");
    const notes = window.prompt("Transition notes", `${row.name} reviewed for ${humanize(target)}.`);
    if (!notes?.trim()) throw new Error("Transition notes are required.");
    const evidenceInput = window.prompt("Evidence references, separated by commas", row.retirement_evidence_json.join(", ")) || "";
    const evidence = evidenceInput.split(",").map((item) => item.trim()).filter(Boolean);
    await transitionSpreadsheet(row.id, target, notes.trim(), evidence);
  });

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one planning-phase-two rollout-page">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning / Fleet Cutover</p>
            <h1>Rollout and Spreadsheet Retirement</h1>
            <p className="page-header__subtitle">Move aircraft through dual-run and verified cutover waves, then retire spreadsheets only when replacement evidence is complete.</p>
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          <div className="planning-phase-one__header-actions">
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Portal counters</Link>
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=migration`}>Migration pilot</Link>
            <button className="btn btn-primary" disabled={busy} onClick={() => void reload()}>Refresh</button>
          </div>
        </header>

        <nav className="winair-subnav" aria-label="Data control views">
          <Link to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Portal counters</Link>
          <Link to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}>WinAir exchange</Link>
          <Link to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=migration`}>Migration pilot</Link>
          <Link className="is-active" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=rollout`}>Fleet rollout</Link>
        </nav>

        {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}

        <section className="planning-metric-grid">
          {[
            ["Groups", dashboard.groups], ["Waves", dashboard.waves], ["Active waves", dashboard.active_waves],
            ["Dual run", dashboard.aircraft_dual_run], ["Cutover", dashboard.aircraft_cutover], ["Verified", dashboard.aircraft_verified],
            ["Complete", dashboard.aircraft_complete], ["On hold", dashboard.aircraft_hold], ["Live sheets", dashboard.spreadsheet_live],
            ["Retired sheets", dashboard.spreadsheet_retired],
          ].map(([label, value]) => <article key={String(label)} className="planning-metric-card"><span className="planning-metric-card__label">{label}</span><strong>{value}</strong></article>)}
        </section>

        <section className="rollout-layout">
          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Rollout structure</h2><p>Create the programme group, then sequence aircraft into controlled waves.</p></div></div>
            <div className="rollout-form-grid">
              <label><span>Group name</span><input className="input" value={groupDraft.name} onChange={(event) => setGroupDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label className="is-wide"><span>Description</span><input className="input" value={groupDraft.description} onChange={(event) => setGroupDraft((current) => ({ ...current, description: event.target.value }))} /></label>
            </div>
            <button className="btn btn-secondary" disabled={busy} onClick={() => void createGroup()}>Create group</button>
            <select className="input rollout-select" value={selectedGroupId} onChange={(event) => { setSelectedGroupId(event.target.value); setSelectedWaveId(""); }}><option value="">Select group</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name} · {group.status}</option>)}</select>
            <div className="rollout-form-grid">
              <label><span>Wave name</span><input className="input" value={waveDraft.name} onChange={(event) => setWaveDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label><span>Sequence</span><input className="input" type="number" min="1" value={waveDraft.sequence_no} onChange={(event) => setWaveDraft((current) => ({ ...current, sequence_no: Number(event.target.value) }))} /></label>
              <label><span>Start</span><input className="input" type="date" value={waveDraft.planned_start} onChange={(event) => setWaveDraft((current) => ({ ...current, planned_start: event.target.value }))} /></label>
              <label><span>End</span><input className="input" type="date" value={waveDraft.planned_end} onChange={(event) => setWaveDraft((current) => ({ ...current, planned_end: event.target.value }))} /></label>
            </div>
            <div className="rollout-aircraft-picker">{aircraft.map((row) => <label key={row.serial_number}><input type="checkbox" checked={selectedAircraft.includes(row.serial_number)} onChange={(event) => setSelectedAircraft((current) => event.target.checked ? [...current, row.serial_number] : current.filter((item) => item !== row.serial_number))} /><span><strong>{row.registration}</strong><small>{row.serial_number} · {row.model || "Unknown model"}</small></span></label>)}</div>
            <button className="btn btn-primary" disabled={busy || !selectedGroup || !selectedAircraft.length} onClick={() => void createWave()}>Create wave</button>
          </article>

          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Wave decision gate</h2><p>Readiness is calculated from portal data and checklist evidence.</p></div>{selectedWave ? <StatusChip value={selectedWave.status} /> : null}</div>
            <select className="input" value={selectedWaveId} onChange={(event) => setSelectedWaveId(event.target.value)}><option value="">Select wave</option>{allWaves.map((wave) => <option key={wave.id} value={wave.id}>#{wave.sequence_no} {wave.name} · {wave.status}</option>)}</select>
            {selectedWave ? <div className="rollout-wave-summary"><div><span>Readiness</span><StatusChip value={selectedWave.readiness_json.status || "NOT_ASSESSED"} /></div><div><span>Aircraft</span><strong>{selectedWave.aircraft.length}</strong></div><div><span>Checklist</span><strong>{Number(selectedWave.readiness_json.metrics?.checklist_complete || 0)}/{Number(selectedWave.readiness_json.metrics?.checklist_items || 0)}</strong></div><div><span>Window</span><strong>{formatDate(selectedWave.planned_start)} – {formatDate(selectedWave.planned_end)}</strong></div></div> : null}
            {selectedWave?.readiness_json.blockers?.length ? <div className="rollout-blockers">{selectedWave.readiness_json.blockers.map((item) => <div key={item}>{item}</div>)}</div> : null}
            <div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy || !selectedWave} onClick={() => void assessWave()}>Reassess</button><button className="btn btn-primary" disabled={busy || !selectedWave || !nextWaveAction[selectedWave.status]} onClick={() => void advanceWave()}>Advance wave</button><button className="btn btn-danger" disabled={busy || !selectedWave || ["COMPLETE", "CANCELLED", "HOLD"].includes(selectedWave.status)} onClick={() => void setWaveHold()}>Hold wave</button></div>
          </article>
        </section>

        {selectedWave ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Aircraft cutover board</h2><p>Each aircraft moves independently through dual-run, cutover, verification and completion.</p></div></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Aircraft</th><th>Status</th><th>Migration</th><th>Dual run</th><th>Cutover</th><th>Verified</th><th>Notes</th><th /></tr></thead><tbody>{selectedWave.aircraft.map((row) => <tr key={row.id}><td><strong>{row.registration}</strong><small>{row.aircraft_serial_number}</small></td><td><StatusChip value={row.status} /></td><td>{row.migration_batch_id ? <code>{row.migration_batch_id.slice(0, 10)}…</code> : "—"}</td><td>{formatDate(row.dual_run_started_at)}</td><td>{formatDate(row.cutover_at)}</td><td>{formatDate(row.verified_at)}</td><td>{row.hold_reason || row.notes || "—"}</td><td><div className="planning-inline-actions"><button className="btn btn-primary" disabled={busy || !nextAircraftAction[row.status]} onClick={() => void advanceAircraft(row)}>{nextAircraftAction[row.status] ? humanize(nextAircraftAction[row.status] as string) : "Complete"}</button><button className="btn btn-secondary" disabled={busy || ["COMPLETE", "HOLD"].includes(row.status)} onClick={() => void holdAircraft(row)}>Hold</button></div></td></tr>)}</tbody></table></div></section> : null}

        {selectedWave ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Rollout evidence checklist</h2><p>Wave-level and aircraft-level controls are retained with evidence and completion identity.</p></div></div><div className="rollout-checklist-grid">{selectedWave.checklist_items.map((item) => <button key={item.id} disabled={busy} onClick={() => void toggleChecklist(item.id, item.status)}><StatusChip value={item.status} /><span><strong>{item.label}</strong><small>{item.aircraft_serial_number ? selectedWave.aircraft.find((row) => row.aircraft_serial_number === item.aircraft_serial_number)?.registration : "Wave-wide"} · {humanize(item.category)}</small></span></button>)}</div></section> : null}

        <section className="rollout-layout">
          <article className="card planning-panel"><div className="planning-panel__header"><div><h2>Spreadsheet register</h2><p>Register every operational workbook before retirement decisions begin.</p></div></div><div className="rollout-form-grid"><label><span>Name</span><input className="input" value={sheetDraft.name} onChange={(event) => setSheetDraft((current) => ({ ...current, name: event.target.value }))} /></label><label><span>Owner</span><input className="input" value={sheetDraft.owner} onChange={(event) => setSheetDraft((current) => ({ ...current, owner: event.target.value }))} /></label><label><span>Location</span><input className="input" value={sheetDraft.location} onChange={(event) => setSheetDraft((current) => ({ ...current, location: event.target.value }))} /></label><label><span>Domain</span><select className="input" value={sheetDraft.data_domain} onChange={(event) => setSheetDraft((current) => ({ ...current, data_domain: event.target.value }))}>{["AIRCRAFT_MASTER", "UTILISATION", "MAINTENANCE_PROGRAM", "FORECAST", "WORK_PACKAGE", "DEFERRAL", "COMPONENT", "TECHNICAL_RECORDS", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select></label><label className="is-wide"><span>Purpose</span><textarea className="input" value={sheetDraft.purpose} onChange={(event) => setSheetDraft((current) => ({ ...current, purpose: event.target.value }))} /></label><label className="is-wide"><span>Replacement route</span><input className="input" value={sheetDraft.replacement_route} onChange={(event) => setSheetDraft((current) => ({ ...current, replacement_route: event.target.value }))} /></label><label className="is-wide"><span>Retirement criteria, one per line</span><textarea className="input" value={sheetDraft.criteria} onChange={(event) => setSheetDraft((current) => ({ ...current, criteria: event.target.value }))} /></label></div><button className="btn btn-primary" disabled={busy} onClick={() => void registerSpreadsheet()}>Register spreadsheet</button></article>

          <article className="card planning-panel"><div className="planning-panel__header"><div><h2>Retirement safeguards</h2><p>Retirement requires a completed rollout wave, no aircraft in dual-run/cutover/hold, a replacement route, criteria, and matching evidence.</p></div></div><div className="spreadsheet-state-guide">{["LIVE", "DUAL_RUN", "READ_ONLY", "RETIRED", "ARCHIVED"].map((value, index) => <div key={value}><strong>{index + 1}</strong><span>{humanize(value)}</span></div>)}</div></article>
        </section>

        <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Spreadsheet retirement board</h2><p>No workbook is deleted; each state change and evidence reference remains in the retirement ledger.</p></div></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Spreadsheet</th><th>Domain</th><th>Owner</th><th>Status</th><th>Replacement</th><th>Evidence</th><th>Last event</th><th /></tr></thead><tbody>{spreadsheets.map((row) => <tr key={row.id}><td><strong>{row.name}</strong><small>{row.purpose}</small></td><td>{humanize(row.data_domain)}</td><td>{row.owner || "—"}</td><td><StatusChip value={row.status} /></td><td>{row.replacement_route || "—"}</td><td>{row.retirement_evidence_json.length}/{row.retirement_criteria_json.length}</td><td>{row.events[0] ? `${humanize(row.events[0].to_status)} · ${formatDate(row.events[0].created_at)}` : "—"}</td><td><button className="btn btn-primary" disabled={busy || !nextSpreadsheetAction[row.status]} onClick={() => void advanceSpreadsheet(row)}>{nextSpreadsheetAction[row.status] ? `Move to ${humanize(nextSpreadsheetAction[row.status] as string)}` : "Archived"}</button></td></tr>)}</tbody></table></div></section>
      </div>
    </DepartmentLayout>
  );
};
