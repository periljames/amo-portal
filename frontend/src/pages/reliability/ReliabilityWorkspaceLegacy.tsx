import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import {
  getFracasCase,
  getReliabilityAlert,
  getReliabilityEvent,
  getReliabilityWorkbench,
  listEngineTrendStatuses,
  listFracasActions,
  listFracasCases,
  listReliabilityAlerts,
  listReliabilityEvents,
  type EngineTrend,
  type FracasAction,
  type FracasCase,
  type ReliabilityAlert,
  type ReliabilityEvent,
  type ReliabilityFreshness,
  type ReliabilityPriority,
  type ReliabilitySeverity,
  type ReliabilityWorkbench,
} from "../../services/reliability";
import ReliabilityReportsView from "./ReliabilityReportsView";
import ReliabilityOperationalControl from "./ReliabilityOperationalControl";
import { FracasGovernancePanel, OccurrenceProvenancePanel, ReliabilityAdvancedView, type AdvancedReliabilityViewId } from "./ReliabilityAdvancedViews";
import "../../styles/reliability-v2.css";

type ViewId =
  | "workbench" | "operations" | "events" | "alerts" | "cases" | "fleet" | "systems"
  | "components" | "engines" | "calculations" | "program" | "changes"
  | "handoffs" | "meetings" | "authority" | "ai" | "compliance"
  | "sources" | "ingestion" | "data-quality" | "reports";

type RouteState = { view: ViewId; entityId: number | null };

const VIEWS = new Set<ViewId>([
  "workbench", "operations", "events", "alerts", "cases", "fleet", "systems", "components",
  "engines", "calculations", "program", "changes", "handoffs", "meetings",
  "authority", "ai", "compliance", "sources", "ingestion", "data-quality", "reports",
]);

const ADVANCED_VIEWS = new Set<AdvancedReliabilityViewId>([
  "compliance", "sources", "ingestion", "data-quality", "fleet", "systems",
  "components", "calculations", "program", "changes", "handoffs", "meetings",
  "authority", "ai",
]);

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusClass(value?: string | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "unknown").toLowerCase().replaceAll(" ", "-")}`;
}

function severityClass(value?: ReliabilitySeverity | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "LOW").toLowerCase()}`;
}

function routeState(pathname: string): RouteState {
  const parts = pathname.split("/reliability")[1]?.split("/").filter(Boolean) || [];
  const requested = (parts[0] || "workbench") as ViewId;
  const view = VIEWS.has(requested) ? requested : "workbench";
  const entityId = parts[1] && /^\d+$/.test(parts[1]) ? Number(parts[1]) : null;
  return { view, entityId };
}

const ReliabilityWorkspacePage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const basePath = `/maintenance/${encodeURIComponent(amoCode)}/reliability`;
  const route = useMemo(() => routeState(location.pathname), [location.pathname]);

  const [workbench, setWorkbench] = useState<ReliabilityWorkbench | null>(null);
  const [events, setEvents] = useState<ReliabilityEvent[]>([]);
  const [alerts, setAlerts] = useState<ReliabilityAlert[]>([]);
  const [cases, setCases] = useState<FracasCase[]>([]);
  const [engines, setEngines] = useState<EngineTrend[]>([]);
  const [event, setEvent] = useState<ReliabilityEvent | null>(null);
  const [alert, setAlert] = useState<ReliabilityAlert | null>(null);
  const [fracasCase, setFracasCase] = useState<FracasCase | null>(null);
  const [actions, setActions] = useState<FracasAction[]>([]);
  const loadKey = `${route.view}:${route.entityId ?? "list"}`;
  const [resolvedKey, setResolvedKey] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<{ key: string; message: string } | null>(null);
  const loading = route.view === "operations" ? false : resolvedKey !== loadKey;
  const error = requestError?.key === loadKey ? requestError.message : null;

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      if (route.view === "operations") return;
      if (route.view === "workbench") {
        const data = await getReliabilityWorkbench(10);
        if (active) setWorkbench(data);
      } else if (route.view === "events") {
        if (route.entityId) {
          const data = await getReliabilityEvent(route.entityId);
          if (active) setEvent(data);
        } else {
          const data = await listReliabilityEvents({ limit: 150 });
          if (active) setEvents(data);
        }
      } else if (route.view === "alerts") {
        if (route.entityId) {
          const data = await getReliabilityAlert(route.entityId);
          if (active) setAlert(data);
        } else {
          const data = await listReliabilityAlerts({ limit: 150 });
          if (active) setAlerts(data);
        }
      } else if (route.view === "cases") {
        if (route.entityId) {
          const [caseData, actionData] = await Promise.all([
            getFracasCase(route.entityId),
            listFracasActions(route.entityId),
          ]);
          if (active) {
            setFracasCase(caseData);
            setActions(actionData);
          }
        } else {
          const data = await listFracasCases({ limit: 150 });
          if (active) setCases(data);
        }
      } else if (route.view === "engines") {
        const data = await listEngineTrendStatuses({ limit: 150 });
        if (active) setEngines(data);
      }
    }

    load()
      .then(() => {
        if (!active) return;
        setRequestError(null);
        setResolvedKey(loadKey);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setRequestError({
          key: loadKey,
          message: caught instanceof Error ? caught.message : "Reliability data could not be loaded.",
        });
        setResolvedKey(loadKey);
      });

    return () => { active = false; };
  }, [loadKey, route.entityId, route.view]);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
      <main className="reliability-v2">
        <header className="reliability-v2__header">
          <div>
            <p className="reliability-v2__eyebrow">Continuing-airworthiness intelligence</p>
            <h1>Reliability</h1>
            <p>Detection, technical investigation, corrective action and measured effectiveness.</p>
          </div>
          <div className="reliability-v2__actions">
            <Link className="btn btn-primary" to={`${basePath}/operations`}>Operational sources</Link>
            <Link className="btn btn-secondary" to={`${basePath}/compliance`}>Compliance control</Link>
            <Link className="btn btn-secondary" to={route.view === "reports" ? basePath : `${basePath}/reports`}>{route.view === "reports" ? "Reliability workbench" : "Controlled reports"}</Link>
          </div>
        </header>

        {loading && <div className="reliability-v2__loading" role="status">Loading authoritative reliability data…</div>}
        {error && <div className="reliability-v2__error" role="alert">{error}</div>}
        {!loading && !error && renderView({
          route,
          basePath,
          workbench,
          events,
          alerts,
          cases,
          engines,
          event,
          alert,
          fracasCase,
          actions,
        })}
      </main>
    </DepartmentLayout>
  );
};

type ViewProps = {
  route: RouteState;
  basePath: string;
  workbench: ReliabilityWorkbench | null;
  events: ReliabilityEvent[];
  alerts: ReliabilityAlert[];
  cases: FracasCase[];
  engines: EngineTrend[];
  event: ReliabilityEvent | null;
  alert: ReliabilityAlert | null;
  fracasCase: FracasCase | null;
  actions: FracasAction[];
};

function renderView(props: ViewProps): React.ReactNode {
  const { route, basePath } = props;
  if (route.view === "operations") return <ReliabilityOperationalControl />;
  if (route.view === "workbench") return props.workbench ? <Workbench data={props.workbench} basePath={basePath} /> : null;
  if (route.view === "events") return props.event ? <><EventDetail item={props.event} basePath={basePath} /><OccurrenceProvenancePanel eventId={props.event.id} /></> : <EventRegister rows={props.events} basePath={basePath} />;
  if (route.view === "alerts") return props.alert ? <AlertDetail item={props.alert} basePath={basePath} /> : <AlertRegister rows={props.alerts} basePath={basePath} />;
  if (route.view === "cases") return props.fracasCase ? <><CaseDetail item={props.fracasCase} actions={props.actions} basePath={basePath} /><FracasGovernancePanel caseId={props.fracasCase.id} /></> : <CaseRegister rows={props.cases} basePath={basePath} />;
  if (route.view === "engines") return <EngineRegister rows={props.engines} />;
  if (route.view === "reports") return <ReliabilityReportsView />;
  if (ADVANCED_VIEWS.has(route.view as AdvancedReliabilityViewId)) return <ReliabilityAdvancedView view={route.view as AdvancedReliabilityViewId} basePath={basePath} />;
  return null;
}

function Workbench({ data, basePath }: { data: ReliabilityWorkbench; basePath: string }) {
  const metrics: Array<[string, number, string]> = [
    ["Critical alerts", data.counts.critical_alerts, "alerts"],
    ["Open alerts", data.counts.open_alerts, "alerts"],
    ["Active FRACAS", data.counts.active_cases, "cases"],
    ["Overdue actions", data.counts.overdue_actions, "cases"],
    ["Engine shifts", data.counts.engine_shifts, "engines"],
    ["Data issues", data.counts.data_quality_issues, "data-quality"],
  ];
  return <>
    <section className="reliability-v2__metric-strip">
      {metrics.map(([label, count, path]) => <Link className="reliability-v2__metric" to={`${basePath}/${path}`} key={label}><span>{label}</span><strong>{count}</strong></Link>)}
    </section>
    <section className="reliability-v2__section">
      <SectionHeading eyebrow="Decision queue" title="What needs attention now" meta={`${data.priorities.length} items`} />
      <div className="reliability-v2__priority-list">
        {data.priorities.length === 0 && <p className="reliability-v2__empty">No triggered priorities. Confirm data freshness before treating the fleet as healthy.</p>}
        {data.priorities.map((item, index) => <PriorityRow key={`${item.kind}-${item.entity_id || index}`} item={item} basePath={basePath} />)}
      </div>
    </section>
    <div className="reliability-v2__split">
      <section className="reliability-v2__section"><SectionHeading eyebrow="Latest evidence" title="Recent occurrences" /><EventTable rows={data.recent_events.slice(0, 8)} basePath={basePath} /></section>
      <section className="reliability-v2__section"><SectionHeading eyebrow="Closed-loop control" title="Active investigations" /><CaseTable rows={data.active_cases.slice(0, 8)} basePath={basePath} /></section>
    </div>
    <section className="reliability-v2__section"><SectionHeading eyebrow="No data, no green" title="Source freshness" /><FreshnessTable rows={data.data_freshness} /></section>
  </>;
}

function PriorityRow({ item, basePath }: { item: ReliabilityPriority; basePath: string }) {
  return <Link className="reliability-v2__priority" to={`${basePath}/${item.relative_path}`}>
    <span className={severityClass(item.severity)}>{item.severity}</span>
    <span><strong>{item.title}</strong><small>{item.summary || item.kind.replaceAll("_", " ")}</small></span>
    <time>{displayDate(item.occurred_at || item.due_date)}</time>
  </Link>;
}

function SectionHeading({ eyebrow, title, meta }: { eyebrow: string; title: string; meta?: string }) {
  return <div className="reliability-v2__section-heading"><div><p className="reliability-v2__eyebrow">{eyebrow}</p><h2>{title}</h2></div>{meta && <span>{meta}</span>}</div>;
}

function EventRegister({ rows, basePath }: { rows: ReliabilityEvent[]; basePath: string }) {
  return <section className="reliability-v2__section"><SectionHeading eyebrow="Canonical evidence" title="Occurrence register" meta={`${rows.length} loaded`} /><EventTable rows={rows} basePath={basePath} /></section>;
}

function EventTable({ rows, basePath }: { rows: ReliabilityEvent[]; basePath: string }) {
  return <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>When</th><th>Aircraft</th><th>Event</th><th>ATA</th><th>Summary</th></tr></thead><tbody>
    {rows.map((row) => <tr key={row.id}><td><Link to={`${basePath}/events/${row.id}`}>{displayDate(row.occurred_at)}</Link></td><td>{row.aircraft_serial_number || "Fleet"}</td><td><span className={severityClass(row.severity)}>{row.event_type}</span></td><td>{row.ata_chapter || "—"}</td><td>{row.description || row.reference_code || "No description"}</td></tr>)}
    {rows.length === 0 && <tr><td colSpan={5}>No occurrence records are available.</td></tr>}
  </tbody></table></div>;
}

function AlertRegister({ rows, basePath }: { rows: ReliabilityAlert[]; basePath: string }) {
  return <section className="reliability-v2__section"><SectionHeading eyebrow="Technical disposition required" title="Alert register" meta={`${rows.length} loaded`} /><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Alert</th><th>Severity</th><th>Status</th><th>Triggered</th><th>Message</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><Link to={`${basePath}/alerts/${row.id}`}>{row.alert_code}</Link></td><td><span className={severityClass(row.severity)}>{row.severity}</span></td><td><span className={statusClass(row.status)}>{row.status}</span></td><td>{displayDate(row.triggered_at)}</td><td>{row.message || "—"}</td></tr>)}{rows.length === 0 && <tr><td colSpan={5}>No alerts are available.</td></tr>}</tbody></table></div></section>;
}

function CaseRegister({ rows, basePath }: { rows: FracasCase[]; basePath: string }) {
  return <section className="reliability-v2__section"><SectionHeading eyebrow="Failure reporting, analysis and corrective action" title="FRACAS register" meta={`${rows.length} loaded`} /><CaseTable rows={rows} basePath={basePath} /></section>;
}

function CaseTable({ rows, basePath }: { rows: FracasCase[]; basePath: string }) {
  return <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Case</th><th>Aircraft</th><th>Status</th><th>Severity</th><th>Updated</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><Link to={`${basePath}/cases/${row.id}`}>{row.title}</Link></td><td>{row.aircraft_serial_number || "Fleet"}</td><td><span className={statusClass(row.status)}>{row.status.replaceAll("_", " ")}</span></td><td><span className={severityClass(row.severity)}>{row.severity || "UNRATED"}</span></td><td>{displayDate(row.updated_at)}</td></tr>)}{rows.length === 0 && <tr><td colSpan={5}>No FRACAS cases are available.</td></tr>}</tbody></table></div>;
}

function EngineRegister({ rows }: { rows: EngineTrend[] }) {
  return <section className="reliability-v2__section"><SectionHeading eyebrow="Condition monitoring" title="Engine trend status" meta={`${rows.length} engines`} /><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Aircraft</th><th>Position</th><th>Engine S/N</th><th>Status</th><th>Last upload</th><th>Last review</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.aircraft_serial_number}</td><td>{row.engine_position}</td><td>{row.engine_serial_number || "—"}</td><td><span className={statusClass(row.current_status)}>{row.current_status || "Not evaluated"}</span></td><td>{row.last_upload_date || "—"}</td><td>{row.last_review_date || "Not reviewed"}</td></tr>)}{rows.length === 0 && <tr><td colSpan={6}>No engine trend status records are available.</td></tr>}</tbody></table></div></section>;
}

function EventDetail({ item, basePath }: { item: ReliabilityEvent; basePath: string }) {
  return <DetailSurface back={`${basePath}/events`} title={`${item.event_type} occurrence`} status={<span className={severityClass(item.severity)}>{item.severity || "UNRATED"}</span>} fields={[["Aircraft", item.aircraft_serial_number || "Fleet"], ["ATA", item.ata_chapter || "—"], ["Reference", item.reference_code || "—"], ["Source", item.source_system || "—"], ["Occurred", displayDate(item.occurred_at)], ["Description", item.description || "No description recorded"]]} />;
}

function AlertDetail({ item, basePath }: { item: ReliabilityAlert; basePath: string }) {
  return <DetailSurface back={`${basePath}/alerts`} title={item.alert_code} status={<><span className={severityClass(item.severity)}>{item.severity}</span><span className={statusClass(item.status)}>{item.status}</span></>} fields={[["Triggered", displayDate(item.triggered_at)], ["Acknowledged", displayDate(item.acknowledged_at)], ["Resolved", displayDate(item.resolved_at)], ["KPI record", item.kpi_id ? String(item.kpi_id) : "—"], ["Threshold set", item.threshold_set_id ? String(item.threshold_set_id) : "—"], ["Technical message", item.message || "No technical message recorded"]]} />;
}

function CaseDetail({ item, actions, basePath }: { item: FracasCase; actions: FracasAction[]; basePath: string }) {
  return <>
    <DetailSurface back={`${basePath}/cases`} title={item.title} status={<><span className={severityClass(item.severity)}>{item.severity || "UNRATED"}</span><span className={statusClass(item.status)}>{item.status.replaceAll("_", " ")}</span></>} fields={[["Aircraft", item.aircraft_serial_number || "Fleet"], ["Classification", item.classification || "Unclassified"], ["Opened", displayDate(item.opened_at)], ["Failure definition", item.description || "Not recorded"], ["Root cause", item.root_cause || "Not yet approved"], ["Corrective action", item.corrective_action_summary || "Not yet approved"], ["Verification", item.verification_notes || "Effectiveness not yet verified"]]} />
    <section className="reliability-v2__section"><SectionHeading eyebrow="Implementation and effectiveness" title="Case actions" meta={`${actions.length} actions`} /><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Action</th><th>Status</th><th>Owner</th><th>Due</th><th>Verified</th></tr></thead><tbody>{actions.map((action) => <tr key={action.id}><td>{action.description}</td><td><span className={statusClass(action.status)}>{action.status.replaceAll("_", " ")}</span></td><td>{action.owner_user_id || "Unassigned"}</td><td>{action.due_date || "—"}</td><td>{displayDate(action.verified_at)}</td></tr>)}{actions.length === 0 && <tr><td colSpan={5}>No corrective or preventive actions have been recorded.</td></tr>}</tbody></table></div></section>
  </>;
}

function DetailSurface({ back, title, status, fields }: { back: string; title: string; status: React.ReactNode; fields: Array<[string, string]> }) {
  return <section className="reliability-v2__section reliability-v2__detail"><div className="reliability-v2__detail-head"><div><Link to={back}>← Back to register</Link><h2>{title}</h2></div><div className="reliability-v2__status-row">{status}</div></div><dl>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>;
}

function FreshnessTable({ rows }: { rows: ReliabilityFreshness[] }) {
  return <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Source</th><th>Status</th><th>Latest record</th><th>Age</th><th>Issue</th></tr></thead><tbody>{rows.map((row) => <tr key={row.source}><td>{row.source}</td><td><span className={statusClass(row.status)}>{row.status}</span></td><td>{displayDate(row.latest_record_at)}</td><td>{row.age_days == null ? "—" : `${row.age_days} days`}</td><td>{row.detail || (row.issue_count ? `${row.issue_count} issues` : "None detected")}</td></tr>)}</tbody></table></div>;
}

export default ReliabilityWorkspacePage;
