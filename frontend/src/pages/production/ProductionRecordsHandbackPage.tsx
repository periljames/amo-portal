import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  addHandbackFinding,
  buildHandback,
  getExecutionDashboard,
  listHandbacks,
  resolveHandbackFinding,
  reviewHandback,
  submitHandback,
  type ExecutionDashboard,
  type Handback,
  type HandbackFinding,
} from "../../services/executionControl";
import { listWorkPackages, type WorkPackage } from "../../services/workPackages";
import { formatCapabilitiesForUi } from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/execution-handback.css";

const emptyDashboard: ExecutionDashboard = {
  open_sessions: 0,
  blocked_sessions: 0,
  open_issues: 0,
  critical_issues: 0,
  draft_handbacks: 0,
  submitted_handbacks: 0,
  rejected_handbacks: 0,
  accepted_handbacks: 0,
};

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const className = normalized.includes("rejected") || normalized.includes("blocked") || normalized.includes("critical") || normalized.includes("open")
    ? "badge badge--danger"
    : normalized.includes("submitted") || normalized.includes("review") || normalized.includes("draft") || normalized.includes("warning")
      ? "badge badge--warning"
      : normalized.includes("accepted") || normalized.includes("ready") || normalized.includes("resolved")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

export const ProductionRecordsHandbackPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const [dashboard, setDashboard] = useState<ExecutionDashboard>(emptyDashboard);
  const [packages, setPackages] = useState<WorkPackage[]>([]);
  const [handbacks, setHandbacks] = useState<Handback[]>([]);
  const [selectedPackageId, setSelectedPackageId] = useState<number | null>(null);
  const [selectedHandbackId, setSelectedHandbackId] = useState("");
  const [findingDraft, setFindingDraft] = useState({ category: "MISSING_EVIDENCE", severity: "ERROR", description: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [dashboardData, packageRows, handbackRows] = await Promise.all([
      getExecutionDashboard(), listWorkPackages(), listHandbacks(),
    ]);
    setDashboard(dashboardData);
    setPackages(packageRows);
    setHandbacks(handbackRows);
    setSelectedPackageId((current) => current ?? packageRows[0]?.id ?? null);
    setSelectedHandbackId((current) => current || handbackRows[0]?.id || "");
  }, []);

  useEffect(() => { void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Records handback could not be loaded.")); }, [reload]);

  const selectedPackage = useMemo(() => packages.find((row) => row.id === selectedPackageId) || packages[0] || null, [packages, selectedPackageId]);
  const selectedHandback = useMemo(() => handbacks.find((row) => row.id === selectedHandbackId) || handbacks[0] || null, [handbacks, selectedHandbackId]);

  const execute = async (success: string, action: () => Promise<unknown>) => {
    setBusy(true); setMessage(null);
    try { await action(); setMessage(success); await reload(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Records handback operation failed."); }
    finally { setBusy(false); }
  };

  const build = () => execute("Records handback manifest built.", async () => {
    if (!selectedPackage) throw new Error("Select a work package.");
    const created = await buildHandback(selectedPackage.id);
    setSelectedHandbackId(created.id);
  });

  const submit = () => execute("Records handback submitted for review.", async () => {
    if (!selectedHandback) return;
    const notes = window.prompt("Submission notes", "Production execution complete; evidence and release records ready for Technical Records review.");
    if (!notes?.trim()) throw new Error("Submission notes are required.");
    await submitHandback(selectedHandback.id, notes.trim());
  });

  const addFinding = () => execute("Records finding raised.", async () => {
    if (!selectedHandback) return;
    if (!findingDraft.description.trim()) throw new Error("Finding description is required.");
    await addHandbackFinding(selectedHandback.id, findingDraft);
    setFindingDraft((current) => ({ ...current, description: "" }));
  });

  const resolveFinding = (finding: HandbackFinding) => execute("Records finding response accepted.", async () => {
    const notes = window.prompt("Production response", "Missing record/evidence corrected and rechecked.");
    if (!notes?.trim()) throw new Error("Response notes are required.");
    await resolveHandbackFinding(finding.id, notes.trim());
  });

  const review = (decision: "ACCEPT" | "REJECT") => execute(`Handback ${decision.toLowerCase()}ed.`, async () => {
    if (!selectedHandback) return;
    const notes = window.prompt("Records review notes", decision === "ACCEPT" ? "Traceability, evidence, CRS, sign-offs and package manifest verified." : "Return to Production for the listed corrections.");
    if (!notes?.trim()) throw new Error("Review notes are required.");
    await reviewHandback(selectedHandback.id, decision, notes.trim());
  });

  const readiness = selectedHandback?.readiness_json || {};

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="production">
      <div className="page planning-production-page planning-phase-one records-handback-page">
        <header className="page-header planning-phase-one__header"><div><p className="planning-phase-one__eyebrow">Production / Technical Records Handover</p><h1>Records Handback</h1><p className="page-header__subtitle">Build the final evidence manifest, clear Records findings, and accept the package into the permanent technical record.</p><p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p></div><div className="planning-phase-one__header-actions"><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/production/work-order-execution`}>Execution control</Link><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/production/release-prep?view=legacy`}>Legacy release prep</Link><button className="btn btn-primary" disabled={busy} onClick={() => void reload()}>Refresh</button></div></header>
        {message ? <div className="alert alert--info">{message}</div> : null}

        <section className="planning-metric-grid">{[
          ["Draft", dashboard.draft_handbacks], ["Awaiting review", dashboard.submitted_handbacks], ["Rejected", dashboard.rejected_handbacks], ["Accepted", dashboard.accepted_handbacks],
        ].map(([label, value]) => <article key={String(label)} className="planning-metric-card"><span className="planning-metric-card__label">{label}</span><strong>{value}</strong></article>)}</section>

        <section className="handback-layout">
          <article className="card planning-panel"><div className="planning-panel__header"><div><h2>Build handback manifest</h2><p>The manifest binds the planning freeze, execution sessions, task condition, evidence, release gates and CRS.</p></div></div><select className="input" value={selectedPackageId || ""} onChange={(event) => setSelectedPackageId(Number(event.target.value) || null)}><option value="">Select work package</option>{packages.map((row) => <option key={row.id} value={row.id}>{row.package_ref} · {row.aircraft_serial_number} · {row.status}</option>)}</select><button className="btn btn-primary" disabled={busy || !selectedPackage} onClick={() => void build()}>Build new manifest version</button></article>

          <article className="card planning-panel"><div className="planning-panel__header"><div><h2>Handback versions</h2><p>Every rejection and resubmission remains traceable by manifest version and hash.</p></div></div><select className="input" value={selectedHandbackId} onChange={(event) => setSelectedHandbackId(event.target.value)}><option value="">Select handback</option>{handbacks.map((row) => <option key={row.id} value={row.id}>Package {row.work_package_id} · v{row.version} · {row.status}</option>)}</select>{selectedHandback ? <div className="handback-summary"><div><span>Status</span><StatusChip value={selectedHandback.status} /></div><div><span>Manifest</span><code>{selectedHandback.manifest_hash.slice(0, 20)}…</code></div><div><span>Readiness</span><StatusChip value={readiness.status || "UNKNOWN"} /></div><div><span>Created</span><strong>{formatDate(selectedHandback.created_at)}</strong></div></div> : null}<div className="planning-inline-actions"><button className="btn btn-primary" disabled={busy || !selectedHandback || !["DRAFT", "REJECTED"].includes(selectedHandback.status)} onClick={() => void submit()}>Submit to Records</button><button className="btn btn-secondary" disabled={busy || !selectedHandback || !["SUBMITTED", "UNDER_REVIEW"].includes(selectedHandback.status)} onClick={() => void review("REJECT")}>Reject</button><button className="btn btn-primary" disabled={busy || !selectedHandback || !["SUBMITTED", "UNDER_REVIEW"].includes(selectedHandback.status)} onClick={() => void review("ACCEPT")}>Accept handback</button></div></article>
        </section>

        {selectedHandback ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Handback readiness</h2><p>Submission is blocked until Production clears every operational and documentary gate.</p></div><StatusChip value={readiness.status || "UNKNOWN"} /></div>{readiness.blockers?.length ? <div className="handback-blockers">{readiness.blockers.map((item) => <div key={item}>{item}</div>)}</div> : <div className="alert alert--success">No current handback blockers.</div>}<pre className="handback-manifest-preview">{JSON.stringify(readiness.metrics || {}, null, 2)}</pre></section> : null}

        {selectedHandback ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Records review findings</h2><p>Technical Records or Quality can return missing or inconsistent evidence without losing the handback history.</p></div></div><div className="handback-finding-form"><select className="input" value={findingDraft.category} onChange={(event) => setFindingDraft((current) => ({ ...current, category: event.target.value }))}>{["MISSING_EVIDENCE", "TASK_INCOMPLETE", "SIGNOFF", "CRS", "CONFIGURATION", "UTILISATION", "DOCUMENT", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select><select className="input" value={findingDraft.severity} onChange={(event) => setFindingDraft((current) => ({ ...current, severity: event.target.value }))}>{["INFO", "WARNING", "ERROR", "CRITICAL"].map((value) => <option key={value}>{value}</option>)}</select><textarea className="input" placeholder="Finding description" value={findingDraft.description} onChange={(event) => setFindingDraft((current) => ({ ...current, description: event.target.value }))} /><button className="btn btn-secondary" disabled={busy || !["SUBMITTED", "UNDER_REVIEW", "REJECTED"].includes(selectedHandback.status)} onClick={() => void addFinding()}>Raise finding</button></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Raised</th><th>Category</th><th>Severity</th><th>Finding</th><th>Status</th><th>Response</th></tr></thead><tbody>{selectedHandback.findings.map((finding) => <tr key={finding.id}><td>{formatDate(finding.raised_at)}</td><td>{humanize(finding.category)}</td><td><StatusChip value={finding.severity} /></td><td>{finding.description}</td><td><StatusChip value={finding.status} /></td><td>{finding.status === "OPEN" ? <button className="btn btn-secondary" disabled={busy} onClick={() => void resolveFinding(finding)}>Respond & resolve</button> : finding.response_notes || "—"}</td></tr>)}</tbody></table></div></section> : null}

        {selectedHandback ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Handback event history</h2><p>Build, submit, review, rejection and acceptance decisions are immutable events.</p></div></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Time</th><th>Event</th><th>From</th><th>To</th><th>Notes</th></tr></thead><tbody>{selectedHandback.events.map((event) => <tr key={event.id}><td>{formatDate(event.created_at)}</td><td>{humanize(event.event_type)}</td><td>{event.from_status || "—"}</td><td>{event.to_status}</td><td>{event.notes || "—"}</td></tr>)}</tbody></table></div></section> : null}
      </div>
    </DepartmentLayout>
  );
};
