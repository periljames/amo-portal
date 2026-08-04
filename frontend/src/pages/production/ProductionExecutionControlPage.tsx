import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  closeExecutionSession,
  getExecutionDashboard,
  listExecutionSessions,
  raiseTaskIssue,
  recordExecutionEvent,
  resolveTaskIssue,
  startExecutionSession,
  type ExecutionDashboard,
  type ExecutionSession,
  type TaskIssue,
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
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(parsed);
}

const StatusChip: React.FC<{ value: string }> = ({ value }) => {
  const normalized = value.toLowerCase();
  const className = normalized.includes("blocked") || normalized.includes("critical") || normalized.includes("open")
    ? "badge badge--danger"
    : normalized.includes("paused") || normalized.includes("medium")
      ? "badge badge--warning"
      : normalized.includes("closed") || normalized.includes("resolved")
        ? "badge badge--success"
        : "badge badge--info";
  return <span className={className}>{humanize(value)}</span>;
};

export const ProductionExecutionControlPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const [dashboard, setDashboard] = useState<ExecutionDashboard>(emptyDashboard);
  const [packages, setPackages] = useState<WorkPackage[]>([]);
  const [sessions, setSessions] = useState<ExecutionSession[]>([]);
  const [selectedPackageId, setSelectedPackageId] = useState<number | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [shiftReference, setShiftReference] = useState("");
  const [station, setStation] = useState("");
  const [issueDraft, setIssueDraft] = useState({ category: "TECHNICAL", severity: "MEDIUM", title: "", description: "", work_order_id: 0 });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [dashboardData, packageRows, sessionRows] = await Promise.all([
      getExecutionDashboard(), listWorkPackages(), listExecutionSessions(),
    ]);
    const executable = packageRows.filter((row) => ["RELEASED", "IN_PROGRESS"].includes(row.status));
    setDashboard(dashboardData);
    setPackages(executable);
    setSessions(sessionRows);
    setSelectedPackageId((current) => current ?? executable[0]?.id ?? null);
    setSelectedSessionId((current) => current || sessionRows[0]?.id || "");
  }, []);

  useEffect(() => { void reload().catch((error) => setMessage(error instanceof Error ? error.message : "Execution control could not be loaded.")); }, [reload]);

  const selectedPackage = useMemo(() => packages.find((row) => row.id === selectedPackageId) || packages[0] || null, [packages, selectedPackageId]);
  const selectedSession = useMemo(() => sessions.find((row) => row.id === selectedSessionId) || sessions[0] || null, [sessions, selectedSessionId]);
  const openIssues = useMemo(() => sessions.flatMap((session) => session.issues).filter((issue) => issue.status === "OPEN"), [sessions]);

  const execute = async (success: string, action: () => Promise<unknown>) => {
    setBusy(true); setMessage(null);
    try { await action(); setMessage(success); await reload(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Execution operation failed."); }
    finally { setBusy(false); }
  };

  const start = () => execute("Execution session opened against the frozen package.", async () => {
    if (!selectedPackage) throw new Error("Select a released work package.");
    const created = await startExecutionSession({ work_package_id: selectedPackage.id, shift_reference: shiftReference || undefined, station: station || undefined });
    setSelectedSessionId(created.id);
  });

  const sessionEvent = (eventType: "SESSION_NOTE" | "PACKAGE_BLOCKED" | "PACKAGE_UNBLOCKED" | "SHIFT_HANDOVER") => execute(`${humanize(eventType)} recorded.`, async () => {
    if (!selectedSession) throw new Error("Select an execution session.");
    const note = window.prompt("Event note", eventType === "SHIFT_HANDOVER" ? "Shift handover condition and outstanding work." : "Production control note.");
    if (!note?.trim()) throw new Error("An event note is required.");
    await recordExecutionEvent(selectedSession.id, { event_type: eventType, payload_json: { note: note.trim() } });
  });

  const raiseIssue = () => execute("Production issue raised.", async () => {
    if (!selectedSession) throw new Error("Select an execution session.");
    const orderId = issueDraft.work_order_id || selectedPackage?.orders[0]?.work_order_id;
    if (!orderId) throw new Error("The selected package has no work order.");
    if (!issueDraft.title.trim() || !issueDraft.description.trim()) throw new Error("Issue title and description are required.");
    await raiseTaskIssue(selectedSession.id, { ...issueDraft, work_order_id: orderId, evidence_json: [] });
    setIssueDraft((current) => ({ ...current, title: "", description: "" }));
  });

  const resolveIssue = (issue: TaskIssue) => execute("Production issue resolved.", async () => {
    const notes = window.prompt("Resolution notes", "Issue rectified and evidence verified.");
    if (!notes?.trim()) throw new Error("Resolution notes are required.");
    await resolveTaskIssue(issue.id, "RECTIFIED", notes.trim());
  });

  const close = () => execute("Execution session closed.", async () => {
    if (!selectedSession) return;
    const notes = window.prompt("Session closure notes", "Shift work completed and outstanding items handed over.");
    if (!notes?.trim()) throw new Error("Closure notes are required.");
    await closeExecutionSession(selectedSession.id, notes.trim());
  });

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="production">
      <div className="page planning-production-page planning-phase-one execution-control-page">
        <header className="page-header planning-phase-one__header"><div><p className="planning-phase-one__eyebrow">Production / Controlled Execution</p><h1>Execution Control</h1><p className="page-header__subtitle">Execute only against a frozen package, record append-only events, control issues, and close each shift cleanly.</p><p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p></div><div className="planning-phase-one__header-actions"><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/production/work-order-execution?view=legacy`}>Legacy execution</Link><Link className="btn btn-secondary" to={`/maintenance/${amoCode}/production/release-prep`}>Records handback</Link><button className="btn btn-primary" disabled={busy} onClick={() => void reload()}>Refresh</button></div></header>
        {message ? <div className="alert alert--info">{message}</div> : null}

        <section className="planning-metric-grid">{[
          ["Open sessions", dashboard.open_sessions], ["Blocked sessions", dashboard.blocked_sessions], ["Open issues", dashboard.open_issues], ["Critical issues", dashboard.critical_issues],
        ].map(([label, value]) => <article key={String(label)} className="planning-metric-card"><span className="planning-metric-card__label">{label}</span><strong>{value}</strong></article>)}</section>

        <section className="execution-layout">
          <article className="card planning-panel"><div className="planning-panel__header"><div><h2>Start execution session</h2><p>Only released packages with an active freeze are available.</p></div></div><label><span>Work package</span><select className="input" value={selectedPackageId || ""} onChange={(event) => setSelectedPackageId(Number(event.target.value) || null)}><option value="">Select package</option>{packages.map((row) => <option key={row.id} value={row.id}>{row.package_ref} · {row.aircraft_serial_number} · {row.title}</option>)}</select></label><div className="execution-form-grid"><label><span>Shift reference</span><input className="input" value={shiftReference} onChange={(event) => setShiftReference(event.target.value)} /></label><label><span>Station</span><input className="input" value={station} onChange={(event) => setStation(event.target.value)} /></label></div><button className="btn btn-primary" disabled={busy || !selectedPackage} onClick={() => void start()}>Open frozen-package session</button></article>

          <article className="card planning-panel"><div className="planning-panel__header"><div><h2>Active session control</h2><p>Notes, blocks, unblocks, and handovers are append-only execution events.</p></div></div><select className="input" value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)}><option value="">Select session</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.id.slice(0, 8)} · Package {row.work_package_id} · {row.status}</option>)}</select>{selectedSession ? <div className="execution-session-summary"><div><span>Status</span><StatusChip value={selectedSession.status} /></div><div><span>Started</span><strong>{formatDate(selectedSession.started_at)}</strong></div><div><span>Freeze</span><code>{selectedSession.package_freeze_id.slice(0, 12)}…</code></div></div> : null}<div className="planning-inline-actions"><button className="btn btn-secondary" disabled={busy || !selectedSession} onClick={() => void sessionEvent("SESSION_NOTE")}>Add note</button><button className="btn btn-secondary" disabled={busy || !selectedSession} onClick={() => void sessionEvent("SHIFT_HANDOVER")}>Handover</button><button className="btn btn-secondary" disabled={busy || !selectedSession} onClick={() => void sessionEvent(selectedSession?.status === "BLOCKED" ? "PACKAGE_UNBLOCKED" : "PACKAGE_BLOCKED")}>{selectedSession?.status === "BLOCKED" ? "Unblock" : "Block"}</button><button className="btn btn-primary" disabled={busy || !selectedSession} onClick={() => void close()}>Close session</button></div></article>
        </section>

        <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Raise production issue</h2><p>Technical, material, tooling, document, access, and human-factor interruptions remain linked to the execution session.</p></div></div><div className="execution-issue-form"><select className="input" value={issueDraft.work_order_id} onChange={(event) => setIssueDraft((current) => ({ ...current, work_order_id: Number(event.target.value) }))}><option value="0">Select work order</option>{selectedPackage?.orders.map((order) => <option key={order.work_order_id} value={order.work_order_id}>{order.wo_number}</option>)}</select><select className="input" value={issueDraft.category} onChange={(event) => setIssueDraft((current) => ({ ...current, category: event.target.value }))}>{["TECHNICAL", "MATERIAL", "TOOL", "DOCUMENT", "ACCESS", "HUMAN_FACTOR", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select><select className="input" value={issueDraft.severity} onChange={(event) => setIssueDraft((current) => ({ ...current, severity: event.target.value }))}>{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => <option key={value}>{value}</option>)}</select><input className="input" placeholder="Issue title" value={issueDraft.title} onChange={(event) => setIssueDraft((current) => ({ ...current, title: event.target.value }))} /><textarea className="input" placeholder="Issue description" value={issueDraft.description} onChange={(event) => setIssueDraft((current) => ({ ...current, description: event.target.value }))} /><button className="btn btn-primary" disabled={busy || !selectedSession} onClick={() => void raiseIssue()}>Raise issue</button></div></section>

        <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Open issue board</h2><p>Sessions cannot close while issues remain open.</p></div></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Raised</th><th>Session</th><th>Severity</th><th>Category</th><th>Issue</th><th>Status</th><th /></tr></thead><tbody>{openIssues.map((issue) => <tr key={issue.id}><td>{formatDate(issue.raised_at)}</td><td>{issue.session_id.slice(0, 8)}</td><td><StatusChip value={issue.severity} /></td><td>{humanize(issue.category)}</td><td><strong>{issue.title}</strong><small>{issue.description}</small></td><td><StatusChip value={issue.status} /></td><td><button className="btn btn-secondary" disabled={busy} onClick={() => void resolveIssue(issue)}>Resolve</button></td></tr>)}</tbody></table></div></section>

        {selectedSession ? <section className="card planning-panel"><div className="planning-panel__header"><div><h2>Session event ledger</h2><p>Append-only operational history for the selected execution session.</p></div></div><div className="table-wrapper"><table className="table table-striped planning-table"><thead><tr><th>Occurred</th><th>Event</th><th>From</th><th>To</th><th>Payload</th></tr></thead><tbody>{selectedSession.events.map((event) => <tr key={event.id}><td>{formatDate(event.occurred_at)}</td><td>{humanize(event.event_type)}</td><td>{event.from_status || "—"}</td><td>{event.to_status || "—"}</td><td><code>{JSON.stringify(event.payload_json)}</code></td></tr>)}</tbody></table></div></section> : null}
      </div>
    </DepartmentLayout>
  );
};
