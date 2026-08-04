import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  approveMigrationBatch,
  commitMigrationBatch,
  createFiveYSlsPilot,
  decideMigrationReconciliation,
  getMigrationSummary,
  listMigrationBatches,
  reconcileMigrationBatch,
  rollbackMigrationBatch,
  stageMigrationRows,
  updateMigrationCheckpoint,
  validateMigrationBatch,
  type MigrationBatch,
  type MigrationDataset,
  type MigrationSummary,
} from "../../services/migrationControl";
import { formatCapabilitiesForUi } from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/planning-phase2.css";
import "../../styles/migration-pilot.css";

const emptySummary: MigrationSummary = {
  batches: 0,
  active_batches: 0,
  open_reconciliation: 0,
  staged_rows: 0,
  applied_rows: 0,
  failed_rows: 0,
};

const sampleRows = JSON.stringify([
  {
    dataset: "AIRCRAFT_MASTER",
    source_key: "5Y-SLS-master",
    payload: { registration: "5Y-SLS", serial_number: "REPLACE-MSN", template: "DHC8-315", make: "De Havilland", model: "DHC8-315" },
  },
  {
    dataset: "UTILISATION",
    source_key: "5Y-SLS-opening",
    payload: { registration: "5Y-SLS", entry_date: "2026-08-04", techlog_no: "OPENING", total_hours: 0, total_cycles: 0 },
  },
], null, 2);

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
  const className = normalized.includes("failed") || normalized.includes("invalid") || normalized.includes("conflict") || normalized.includes("blocked")
    ? "badge badge--danger"
    : normalized.includes("staged") || normalized.includes("pending") || normalized.includes("partial")
      ? "badge badge--warning"
      : normalized.includes("complete") || normalized.includes("approved") || normalized.includes("committed") || normalized.includes("matched") || normalized.includes("applied")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

export const PlanningMigrationPilotPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const [summary, setSummary] = useState<MigrationSummary>(emptySummary);
  const [batches, setBatches] = useState<MigrationBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [stagingText, setStagingText] = useState(sampleRows);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [summaryData, batchRows] = await Promise.all([getMigrationSummary(), listMigrationBatches()]);
    setSummary(summaryData);
    setBatches(batchRows);
    setSelectedBatchId((current) => current || batchRows[0]?.id || "");
  }, []);

  useEffect(() => {
    void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Migration controls could not be loaded."));
  }, [reload]);

  const selected = useMemo(
    () => batches.find((batch) => batch.id === selectedBatchId) || batches[0] || null,
    [batches, selectedBatchId],
  );

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setMessage(label);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${label} failed.`);
    } finally {
      setBusy(false);
    }
  };

  const createPilot = () => run(
    "5Y-SLS pilot batch created.",
    async () => {
      const batch = await createFiveYSlsPilot(sourceReference || undefined);
      setSelectedBatchId(batch.id);
    },
  );

  const stage = () => run(
    "Source rows staged.",
    async () => {
      if (!selected) throw new Error("Create or select a migration batch first.");
      const parsed = JSON.parse(stagingText) as Array<{
        dataset: MigrationDataset;
        source_key: string;
        payload: Record<string, unknown>;
      }>;
      if (!Array.isArray(parsed) || !parsed.length) throw new Error("Staging JSON must be a non-empty array.");
      await stageMigrationRows(selected.id, parsed, false);
    },
  );

  const lifecycle = (operation: "VALIDATE" | "RECONCILE" | "APPROVE" | "COMMIT" | "ROLLBACK") => run(
    `${humanize(operation)} completed.`,
    async () => {
      if (!selected) throw new Error("Select a migration batch first.");
      if (operation === "VALIDATE") await validateMigrationBatch(selected.id);
      if (operation === "RECONCILE") await reconcileMigrationBatch(selected.id);
      if (operation === "APPROVE") {
        const notes = window.prompt("Approval notes", "5Y-SLS pilot reviewed against source evidence and cutover checkpoints.");
        if (!notes?.trim()) throw new Error("Approval notes are required.");
        await approveMigrationBatch(selected.id, notes.trim());
      }
      if (operation === "COMMIT") {
        if (!window.confirm("Commit all approved, non-conflicting 5Y-SLS migration rows?")) return;
        await commitMigrationBatch(selected.id, "Approved pilot cutover commit.", false);
      }
      if (operation === "ROLLBACK") {
        const reason = window.prompt("Rollback reason");
        if (!reason?.trim()) throw new Error("Rollback reason is required.");
        await rollbackMigrationBatch(selected.id, reason.trim());
      }
    },
  );

  const resolveRecon = (itemId: string, resolution: "ACCEPT_SOURCE" | "KEEP_LOCAL" | "WAIVE") => run(
    "Reconciliation item resolved.",
    async () => {
      if (!selected) return;
      const notes = window.prompt("Resolution notes", resolution === "KEEP_LOCAL" ? "Controlled portal record retained." : "Source evidence reviewed.");
      if (!notes?.trim()) throw new Error("Resolution notes are required.");
      await decideMigrationReconciliation(selected.id, itemId, resolution, notes.trim());
    },
  );

  const toggleCheckpoint = (checkpointKey: string, currentStatus: string) => run(
    "Cutover checkpoint updated.",
    async () => {
      if (!selected) return;
      const next = currentStatus === "COMPLETE" ? "PENDING" : "COMPLETE";
      const notes = window.prompt("Checkpoint evidence or notes", next === "COMPLETE" ? "Verified for 5Y-SLS pilot." : "Reopened for review.");
      await updateMigrationCheckpoint(selected.id, checkpointKey, next, notes || undefined, []);
    },
  );

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one planning-phase-two migration-page">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning / Controlled Migration</p>
            <h1>5Y-SLS Pilot Migration</h1>
            <p className="page-header__subtitle">Stage, validate, reconcile, approve, commit, and evidence the first aircraft cutover without overwriting controlled records.</p>
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          <div className="planning-phase-one__header-actions">
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Portal counters</Link>
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}>WinAir exchange</Link>
            <button className="btn btn-primary" disabled={busy} onClick={() => void reload()}>Refresh</button>
          </div>
        </header>

        <nav className="winair-subnav" aria-label="Data control views">
          <Link to={`/maintenance/${amoCode}/planning/utilisation-monitoring`}>Portal counters</Link>
          <Link to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=winair`}>WinAir exchange</Link>
          <Link className="is-active" to={`/maintenance/${amoCode}/planning/utilisation-monitoring?view=migration`}>Migration pilot</Link>
        </nav>

        {message ? <div className="alert alert--info planning-phase-two__message">{message}</div> : null}

        <section className="planning-metric-grid">
          {[
            ["Batches", summary.batches],
            ["Active", summary.active_batches],
            ["Open reconciliation", summary.open_reconciliation],
            ["Staged rows", summary.staged_rows],
            ["Applied rows", summary.applied_rows],
            ["Failed rows", summary.failed_rows],
          ].map(([label, value]) => <article key={String(label)} className="planning-metric-card"><span className="planning-metric-card__label">{label}</span><strong>{value}</strong></article>)}
        </section>

        <section className="migration-layout">
          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Pilot batches</h2><p>The 5Y-SLS preset creates the controlled scope and cutover checklist.</p></div></div>
            <div className="migration-create-row">
              <input className="input" value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} placeholder="Source workbook, export, or evidence reference" />
              <button className="btn btn-primary" disabled={busy} onClick={() => void createPilot()}>Create 5Y-SLS pilot</button>
            </div>
            <div className="migration-batch-list">
              {batches.map((batch) => (
                <button key={batch.id} className={selected?.id === batch.id ? "is-selected" : ""} onClick={() => setSelectedBatchId(batch.id)}>
                  <span><strong>{batch.name}</strong><small>{batch.target_registration || batch.target_aircraft_serial_number || "Unmapped"} · {formatDate(batch.updated_at)}</small></span>
                  <StatusChip value={batch.status} />
                </button>
              ))}
            </div>
          </article>

          <article className="card planning-panel">
            <div className="planning-panel__header"><div><h2>Stage source rows</h2><p>Paste normalized JSON rows from the workbook/export parser. No source row is committed at this step.</p></div></div>
            <textarea className="input migration-json" value={stagingText} onChange={(event) => setStagingText(event.target.value)} spellCheck={false} />
            <div className="planning-inline-actions">
              <button className="btn btn-primary" disabled={busy || !selected} onClick={() => void stage()}>Stage rows</button>
              <button className="btn btn-secondary" disabled={busy || !selected} onClick={() => void lifecycle("VALIDATE")}>Validate</button>
              <button className="btn btn-secondary" disabled={busy || !selected} onClick={() => void lifecycle("RECONCILE")}>Reconcile</button>
            </div>
          </article>
        </section>

        {selected ? (
          <>
            <section className="card planning-panel">
              <div className="planning-panel__header"><div><h2>Cutover readiness</h2><p>Approval remains blocked until every checkpoint is complete or explicitly not applicable.</p></div><StatusChip value={selected.status} /></div>
              <div className="migration-checkpoints">
                {selected.checkpoints.map((checkpoint) => (
                  <button key={checkpoint.id} onClick={() => void toggleCheckpoint(checkpoint.checkpoint_key, checkpoint.status)} disabled={busy}>
                    <StatusChip value={checkpoint.status} />
                    <span><strong>{checkpoint.label}</strong><small>{checkpoint.notes || "Click to record verification."}</small></span>
                  </button>
                ))}
              </div>
              <div className="planning-inline-actions migration-gate-actions">
                <button className="btn btn-secondary" disabled={busy || selected.status !== "RECONCILED"} onClick={() => void lifecycle("APPROVE")}>Quality approve</button>
                <button className="btn btn-primary" disabled={busy || selected.status !== "APPROVED"} onClick={() => void lifecycle("COMMIT")}>Commit pilot</button>
                <button className="btn btn-danger" disabled={busy || !["COMMITTED", "PARTIAL"].includes(selected.status)} onClick={() => void lifecycle("ROLLBACK")}>Controlled rollback</button>
              </div>
            </section>

            <section className="card planning-panel">
              <div className="planning-panel__header"><div><h2>Reconciliation queue</h2><p>Source differences require an explicit decision; controlled portal records are never overwritten automatically.</p></div></div>
              <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Dataset</th><th>Category</th><th>Summary</th><th>Differences</th><th>Decision</th></tr></thead><tbody>{selected.reconciliation_items.map((item) => <tr key={item.id}><td>{selected.rows.find((row) => row.id === item.row_id)?.dataset || "—"}</td><td><StatusChip value={item.category} /></td><td>{item.summary}</td><td><pre className="migration-diff">{JSON.stringify(item.differences_json, null, 2)}</pre></td><td>{item.status === "OPEN" ? <div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => void resolveRecon(item.id, "WAIVE")}>Waive</button><button className="btn btn-secondary" disabled={busy} onClick={() => void resolveRecon(item.id, "KEEP_LOCAL")}>Keep portal</button><button className="btn btn-primary" disabled={busy} onClick={() => void resolveRecon(item.id, "ACCEPT_SOURCE")}>Accept source</button></div> : <StatusChip value={item.status} />}</td></tr>)}</tbody></table></div>
            </section>

            <section className="card planning-panel">
              <div className="planning-panel__header"><div><h2>Staged row register</h2><p>Every source row retains normalized values, validation condition, intended action, and applied object reference.</p></div></div>
              <div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>#</th><th>Dataset</th><th>Source key</th><th>Status</th><th>Action</th><th>Local object</th><th>Errors</th></tr></thead><tbody>{selected.rows.map((row) => <tr key={row.id}><td>{row.source_row_number}</td><td>{humanize(row.dataset)}</td><td><code>{row.source_key}</code></td><td><StatusChip value={row.status} /></td><td>{humanize(row.action)}</td><td>{row.local_object_type ? `${row.local_object_type} ${row.local_object_id || ""}` : "—"}</td><td>{row.errors_json.map(String).join("; ") || "—"}</td></tr>)}</tbody></table></div>
            </section>
          </>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};
