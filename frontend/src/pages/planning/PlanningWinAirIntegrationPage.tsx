import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  listIntegrationConfigs,
  type IntegrationConfig,
} from "../../services/integrations";
import {
  createWinAirProfile,
  decideWinAirConflict,
  exportWinAirSnapshot,
  getWinAirDashboard,
  listWinAirConflicts,
  listWinAirProfiles,
  listWinAirRuns,
  reconcileWinAirProfile,
  updateWinAirProfile,
  type WinAirAuthority,
  type WinAirConflict,
  type WinAirDashboard,
  type WinAirDataset,
  type WinAirProfile,
  type WinAirRun,
} from "../../services/winairIntegration";
import { formatCapabilitiesForUi } from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/planning-phase2.css";
import "../../styles/winair-integration.css";

const DATASETS: WinAirDataset[] = [
  "AIRCRAFT_MASTER",
  "AIRCRAFT_COUNTER",
  "FLIGHT_LOG",
  "MAINTENANCE_DUE",
  "INSPECTION_STATUS",
  "DEFERRAL",
];

const defaultAuthority: Partial<Record<WinAirDataset, WinAirAuthority>> = {
  AIRCRAFT_MASTER: "PORTAL",
  AIRCRAFT_COUNTER: "WINAIR",
  FLIGHT_LOG: "WINAIR",
  MAINTENANCE_DUE: "PORTAL",
  INSPECTION_STATUS: "PORTAL",
  DEFERRAL: "PORTAL",
};

const emptyDashboard: WinAirDashboard = {
  profiles: 0,
  active_profiles: 0,
  shadow_profiles: 0,
  open_conflicts: 0,
  failed_records: 0,
  pending_outbox: 0,
  dataset_counts: {},
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
  const className = normalized.includes("failed") || normalized.includes("conflict") || normalized.includes("disabled")
    ? "badge badge--danger"
    : normalized.includes("partial") || normalized.includes("shadow") || normalized.includes("pending")
      ? "badge badge--warning"
      : normalized.includes("active") || normalized.includes("complete") || normalized.includes("applied")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

export const PlanningWinAirIntegrationPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const [dashboard, setDashboard] = useState<WinAirDashboard>(emptyDashboard);
  const [profiles, setProfiles] = useState<WinAirProfile[]>([]);
  const [runs, setRuns] = useState<WinAirRun[]>([]);
  const [conflicts, setConflicts] = useState<WinAirConflict[]>([]);
  const [configs, setConfigs] = useState<IntegrationConfig[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [profileDraft, setProfileDraft] = useState({
    integration_config_id: "",
    name: "WinAir Flight Log Exchange",
    mode: "SHADOW" as "SHADOW" | "ACTIVE",
    transport: "API" as "API" | "FILE" | "WEBHOOK",
    direction: "BIDIRECTIONAL" as "BIDIRECTIONAL" | "INBOUND_ONLY" | "OUTBOUND_ONLY",
    hours_tolerance: 0.05,
    cycles_tolerance: 0,
    authority_json: { ...defaultAuthority },
  });

  const reload = useCallback(async () => {
    const [dashboardData, profileRows, runRows, conflictRows] = await Promise.all([
      getWinAirDashboard(),
      listWinAirProfiles(),
      listWinAirRuns(undefined, 100),
      listWinAirConflicts(undefined, "OPEN"),
    ]);
    setDashboard(dashboardData);
    setProfiles(profileRows);
    setRuns(runRows);
    setConflicts(conflictRows);
    setSelectedProfileId((current) => current || profileRows[0]?.id || "");
    try {
      const configRows = await listIntegrationConfigs();
      const winairRows = configRows.filter((config) => config.integration_key.toLowerCase().includes("winair"));
      setConfigs(winairRows);
      setProfileDraft((current) => ({
        ...current,
        integration_config_id: current.integration_config_id || winairRows[0]?.id || "",
      }));
    } catch {
      setConfigs([]);
    }
  }, []);

  useEffect(() => {
    void reload().catch((error) => setMessage(error instanceof Error ? error.message : "WinAir controls could not be loaded."));
  }, [reload]);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) || profiles[0] || null,
    [profiles, selectedProfileId],
  );

  const createProfile = async () => {
    if (!profileDraft.integration_config_id) {
      setMessage("Create or select a WinAir integration configuration first.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const profile = await createWinAirProfile(profileDraft);
      setSelectedProfileId(profile.id);
      setMessage(`${profile.name} created in ${profile.mode.toLowerCase()} mode.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "WinAir profile could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const runExport = async () => {
    if (!selectedProfile) return;
    setBusy(true);
    setMessage(null);
    try {
      const run = await exportWinAirSnapshot(selectedProfile.id, { horizon_days: 90 });
      setMessage(`Export run ${run.id} completed with ${run.counts_json.exported || 0} record(s) queued.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "WinAir export failed.");
    } finally {
      setBusy(false);
    }
  };

  const runReconcile = async () => {
    if (!selectedProfile) return;
    setBusy(true);
    setMessage(null);
    try {
      const run = await reconcileWinAirProfile(selectedProfile.id);
      setMessage(`Reconciliation ${run.id} completed with ${run.counts_json.conflicts || 0} conflict(s).`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "WinAir reconciliation failed.");
    } finally {
      setBusy(false);
    }
  };

  const toggleMode = async () => {
    if (!selectedProfile) return;
    const nextMode = selectedProfile.mode === "SHADOW" ? "ACTIVE" : "SHADOW";
    const confirmation = nextMode === "ACTIVE"
      ? window.confirm("Activate automatic application of non-conflicting WinAir flight counters? Existing ledger entries will still require correction approval.")
      : true;
    if (!confirmation) return;
    setBusy(true);
    try {
      await updateWinAirProfile(selectedProfile.id, { mode: nextMode });
      setMessage(`${selectedProfile.name} changed to ${nextMode.toLowerCase()} mode.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Profile mode could not be changed.");
    } finally {
      setBusy(false);
    }
  };

  const resolveConflict = async (conflict: WinAirConflict, decision: "ACCEPT_EXTERNAL" | "KEEP_LOCAL" | "IGNORED") => {
    const notes = window.prompt(
      decision === "ACCEPT_EXTERNAL"
        ? "Record the evidence supporting acceptance. Existing ledger entries will become correction requests."
        : "Record the resolution reason.",
      decision === "KEEP_LOCAL" ? "Portal record retained as the controlled source." : "Reviewed in WinAir exchange control.",
    );
    if (!notes?.trim()) return;
    setBusy(true);
    try {
      await decideWinAirConflict(conflict.id, decision, notes.trim());
      setMessage(`${humanize(conflict.conflict_type)} resolved as ${humanize(decision)}.`);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Conflict resolution failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one planning-phase-two winair-page">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning / Data Exchange</p>
            <h1>WinAir Exchange Control</h1>
            <p className="page-header__subtitle">Shadow-first counter ingestion, outbound tech-dispatch snapshots, and controlled conflict resolution.</p>
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          <div className="planning-phase-one__header-actions">
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Portal counters</Link>
            <button className="btn btn-secondary" disabled={busy} onClick={() => void reload()}>Refresh</button>
            <button className="btn btn-primary" disabled={busy || !selectedProfile} onClick={() => void runReconcile()}>Reconcile</button>
          </div>
        </header>

        <nav className="winair-subnav" aria-label="Utilisation control views">
          <Link to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Portal counters</Link>
          <Link className="is-active" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}>WinAir exchange</Link>
        </nav>

        {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}

        <section className="planning-metric-grid">
          {[
            ["Profiles", dashboard.profiles],
            ["Active", dashboard.active_profiles],
            ["Shadow mode", dashboard.shadow_profiles],
            ["Open conflicts", dashboard.open_conflicts],
            ["Failed records", dashboard.failed_records],
            ["Pending outbox", dashboard.pending_outbox],
          ].map(([label, value]) => (
            <article key={String(label)} className={`planning-metric-card ${Number(value) > 0 && String(label).includes("conflict") ? "is-danger" : ""}`}>
              <span className="planning-metric-card__label">{label}</span><strong>{value}</strong>
            </article>
          ))}
        </section>

        <section className="winair-layout">
          <article className="card planning-panel winair-profile-panel">
            <div className="planning-panel__header"><div><h2>Connection profiles</h2><p>Profiles define transport, source authority, tolerances, and shadow or active application.</p></div></div>
            <div className="winair-profile-list">
              {profiles.map((profile) => (
                <button key={profile.id} className={selectedProfile?.id === profile.id ? "is-selected" : ""} onClick={() => setSelectedProfileId(profile.id)}>
                  <span><strong>{profile.name}</strong><small>{profile.transport} · {profile.direction}</small></span>
                  <span><StatusChip value={profile.status} /><StatusChip value={profile.mode} /></span>
                </button>
              ))}
              {!profiles.length ? <div className="planning-empty-state"><strong>No WinAir profile</strong><span>Create the tenant connection profile below.</span></div> : null}
            </div>

            {selectedProfile ? (
              <div className="winair-profile-detail">
                <div><span>Last successful exchange</span><strong>{formatDate(selectedProfile.last_success_at)}</strong></div>
                <div><span>Counter tolerance</span><strong>{selectedProfile.hours_tolerance} FH · {selectedProfile.cycles_tolerance} FC</strong></div>
                <div><span>Latest cursor</span><code>{JSON.stringify(selectedProfile.last_cursor_json || {})}</code></div>
                {selectedProfile.last_error ? <div className="alert alert--danger">{selectedProfile.last_error}</div> : null}
                <div className="planning-inline-actions">
                  <button className="btn btn-secondary" disabled={busy} onClick={() => void toggleMode()}>{selectedProfile.mode === "SHADOW" ? "Activate safe apply" : "Return to shadow"}</button>
                  <button className="btn btn-primary" disabled={busy} onClick={() => void runExport()}>Queue 90-day dispatch export</button>
                </div>
              </div>
            ) : null}
          </article>

          <article className="card planning-panel winair-create-panel">
            <div className="planning-panel__header"><div><h2>Create profile</h2><p>A generic WinAir integration configuration must exist before a profile can be activated.</p></div></div>
            <div className="winair-form-grid">
              <label><span>Integration config</span><select className="input" value={profileDraft.integration_config_id} onChange={(event) => setProfileDraft((current) => ({ ...current, integration_config_id: event.target.value }))}><option value="">Select WinAir config</option>{configs.map((config) => <option key={config.id} value={config.id}>{config.display_name}</option>)}</select></label>
              <label><span>Profile name</span><input className="input" value={profileDraft.name} onChange={(event) => setProfileDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label><span>Mode</span><select className="input" value={profileDraft.mode} onChange={(event) => setProfileDraft((current) => ({ ...current, mode: event.target.value as "SHADOW" | "ACTIVE" }))}><option value="SHADOW">Shadow first</option><option value="ACTIVE">Active safe apply</option></select></label>
              <label><span>Transport</span><select className="input" value={profileDraft.transport} onChange={(event) => setProfileDraft((current) => ({ ...current, transport: event.target.value as "API" | "FILE" | "WEBHOOK" }))}><option>API</option><option>FILE</option><option>WEBHOOK</option></select></label>
              <label><span>Hours tolerance</span><input className="input" type="number" min="0" step="0.01" value={profileDraft.hours_tolerance} onChange={(event) => setProfileDraft((current) => ({ ...current, hours_tolerance: Number(event.target.value) }))} /></label>
              <label><span>Cycles tolerance</span><input className="input" type="number" min="0" step="1" value={profileDraft.cycles_tolerance} onChange={(event) => setProfileDraft((current) => ({ ...current, cycles_tolerance: Number(event.target.value) }))} /></label>
            </div>
            <div className="winair-authority-grid">
              {DATASETS.map((dataset) => (
                <label key={dataset}><span>{humanize(dataset)}</span><select className="input" value={profileDraft.authority_json[dataset] || "PORTAL"} onChange={(event) => setProfileDraft((current) => ({ ...current, authority_json: { ...current.authority_json, [dataset]: event.target.value as WinAirAuthority } }))}><option value="PORTAL">Portal authoritative</option><option value="WINAIR">WinAir authoritative</option><option value="SHARED">Shared / reconcile</option></select></label>
              ))}
            </div>
            {!configs.length ? <p className="text-muted">An AMO administrator must first create an integration configuration with key `winair`, `winair-v7`, or `winair_flight_ops`.</p> : null}
            <button className="btn btn-primary" disabled={busy || !profileDraft.integration_config_id} onClick={() => void createProfile()}>Create controlled profile</button>
          </article>
        </section>

        <section className="card planning-panel">
          <div className="planning-panel__header"><div><h2>Open conflicts</h2><p>No external difference is silently accepted. Existing accepted ledger rows enter the correction approval workflow.</p></div></div>
          <div className="table-wrapper">
            <table className="table table-striped planning-table">
              <thead><tr><th>Created</th><th>Dataset</th><th>External key</th><th>Conflict</th><th>Differences</th><th>Decision</th></tr></thead>
              <tbody>{conflicts.map((conflict) => (
                <tr key={conflict.id}>
                  <td>{formatDate(conflict.created_at)}</td>
                  <td>{humanize(conflict.dataset)}</td>
                  <td><code>{conflict.external_key}</code></td>
                  <td><StatusChip value={conflict.conflict_type} /></td>
                  <td><pre className="winair-diff">{JSON.stringify(conflict.field_differences_json, null, 2)}</pre></td>
                  <td><div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => void resolveConflict(conflict, "IGNORE")}>Ignore</button><button className="btn btn-secondary" disabled={busy} onClick={() => void resolveConflict(conflict, "KEEP_LOCAL")}>Keep portal</button><button className="btn btn-primary" disabled={busy} onClick={() => void resolveConflict(conflict, "ACCEPT_EXTERNAL")}>Accept external</button></div></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {!conflicts.length ? <div className="planning-empty-state"><strong>No open conflicts</strong><span>Current mappings are reconciled.</span></div> : null}
        </section>

        <section className="card planning-panel">
          <div className="planning-panel__header"><div><h2>Exchange history</h2><p>Inbound, outbound, dry-run, and reconciliation executions remain traceable.</p></div></div>
          <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Started</th><th>Profile</th><th>Type</th><th>Status</th><th>Datasets</th><th>Applied</th><th>Conflicts</th><th>Exported</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td>{formatDate(run.started_at)}</td><td>{profiles.find((profile) => profile.id === run.profile_id)?.name || run.profile_id}</td><td>{humanize(run.run_type)}</td><td><StatusChip value={run.status} /></td><td>{run.requested_datasets_json.map(humanize).join(", ")}</td><td>{run.counts_json.applied || 0}</td><td>{run.counts_json.conflicts || 0}</td><td>{run.counts_json.exported || 0}</td></tr>)}</tbody></table></div>
        </section>
      </div>
    </DepartmentLayout>
  );
};
