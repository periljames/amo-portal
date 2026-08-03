import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  addEffectivenessReview,
  addFracasEvidence,
  bootstrapReliability,
  createReliabilityAiReview,
  createReliabilityAuthoritySubmission,
  createReliabilityChange,
  createReliabilityHandoff,
  createReliabilityMeeting,
  createReliabilityMeetingDecision,
  createReliabilityMetricDefinition,
  createReliabilityProgramme,
  createReliabilityProgrammeVersion,
  createReliabilitySource,
  createReliabilityThresholdVersion,
  decideReliabilityAiReview,
  executeReliabilityCalculation,
  getFracasLifecycle,
  getOccurrenceProvenance,
  getReliabilityAnalytics,
  getReliabilityCapabilities,
  getReliabilityCompliance,
  harvestInternalReliabilitySources,
  ingestReliabilitySource,
  listEffectivenessReviews,
  listFracasEvidence,
  listFracasStageEvents,
  listReliabilityAiReviews,
  listReliabilityAuthoritySubmissions,
  listReliabilityAuditEvents,
  listReliabilityCalculationRuns,
  listReliabilityChanges,
  listReliabilityDataQualityIssues,
  listReliabilityHandoffs,
  listReliabilityIngestionBatches,
  listReliabilityMeetings,
  listReliabilityMetricDefinitions,
  listReliabilityProgrammes,
  listReliabilityProgrammeVersions,
  listReliabilitySources,
  listReliabilityThresholdVersions,
  resolveReliabilityDataQualityIssue,
  runDueReliabilityCalculations,
  simulateReliabilityChange,
  transitionFracasLifecycle,
  transitionReliabilityAiReview,
  transitionReliabilityAuthoritySubmission,
  transitionReliabilityChange,
  transitionReliabilityHandoff,
  transitionReliabilityMeeting,
  transitionReliabilityProgrammeVersion,
  transitionReliabilityThresholdVersion,
  updateFracasLifecycle,
  type EffectivenessReview,
  type FracasEvidence,
  type FracasLifecycle,
  type FracasStageEvent,
  type OccurrenceProvenance,
  type ReliabilityAiReview,
  type ReliabilityAnalytics,
  type ReliabilityAuthoritySubmission,
  type ReliabilityAuditEvent,
  type ReliabilityCalculationRun,
  type ReliabilityCapabilitySnapshot,
  type ReliabilityChangeProposal,
  type ReliabilityCompliance,
  type ReliabilityDataQualityIssue,
  type ReliabilityHandoff,
  type ReliabilityIngestionBatch,
  type ReliabilityMeeting,
  type ReliabilityMetricDefinition,
  type ReliabilityProgramme,
  type ReliabilityProgrammeVersion,
  type ReliabilitySource,
  type ReliabilityThresholdVersion,
} from "../../services/reliability";

export type AdvancedReliabilityViewId =
  | "compliance"
  | "sources"
  | "ingestion"
  | "data-quality"
  | "fleet"
  | "systems"
  | "components"
  | "calculations"
  | "program"
  | "changes"
  | "handoffs"
  | "meetings"
  | "authority"
  | "ai";

const EMPTY_CAPABILITIES: ReliabilityCapabilitySnapshot = { capabilities: [], superuser: false };
const EVENT_TYPES = [
  "DEFECT",
  "REPEAT_DEFECT",
  "PILOT_REPORT",
  "TECHNICAL_DELAY",
  "TECHNICAL_CANCELLATION",
  "RETURN_TO_GATE",
  "AIR_TURNBACK",
  "DIVERSION",
  "IN_FLIGHT_SHUTDOWN",
  "MEL_DEFERRAL",
  "CDL_DEFERRAL",
  "UNSCHEDULED_REMOVAL",
  "SHOP_FINDING",
  "NO_FAULT_FOUND",
  "EHM_ALERT",
  "MAINTENANCE_ERROR",
  "SUPPLIER_ESCAPE",
  "SAFETY_EVENT",
];
const FRACAS_STAGES = [
  "TRIAGE",
  "ACCEPTED",
  "REJECTED",
  "MERGED",
  "CONTAINMENT",
  "INVESTIGATION",
  "ROOT_CAUSE_REVIEW",
  "ACTION_APPROVAL",
  "IMPLEMENTATION",
  "EFFECTIVENESS",
  "CLOSED",
  "REOPENED",
];

function today(offsetDays = 0): string {
  const value = new Date();
  value.setDate(value.getDate() + offsetDays);
  return value.toISOString().slice(0, 10);
}

function localDateTime(offsetHours = 0): string {
  const value = new Date(Date.now() + offsetHours * 60 * 60 * 1000);
  const adjusted = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 16);
}

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusClass(value?: string | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "unknown").toLowerCase().replaceAll("_", "-").replaceAll(" ", "-")}`;
}

function jsonText(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseJson(value: FormDataEntryValue | null, fallback: unknown): unknown {
  const raw = String(value || "").trim();
  if (!raw) return fallback;
  return JSON.parse(raw) as unknown;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The Reliability request failed.";
}

function hasCapability(snapshot: ReliabilityCapabilitySnapshot, capability: string): boolean {
  return snapshot.superuser || snapshot.capabilities.includes(capability);
}

function useReliabilityCapabilities(): ReliabilityCapabilitySnapshot {
  const [snapshot, setSnapshot] = useState<ReliabilityCapabilitySnapshot>(EMPTY_CAPABILITIES);
  useEffect(() => {
    let active = true;
    getReliabilityCapabilities()
      .then((value) => { if (active) setSnapshot(value); })
      .catch(() => { if (active) setSnapshot(EMPTY_CAPABILITIES); });
    return () => { active = false; };
  }, []);
  return snapshot;
}

function useResource<T>(loader: () => Promise<T>, dependencies: React.DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    loader()
      .then((value) => {
        if (!active) return;
        setData(value);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setError(errorMessage(caught));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
    // The caller controls stable dependency values explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, revision]);
  return { data, error, loading, refresh };
}

function PageHeading({ eyebrow, title, detail, actions }: { eyebrow: string; title: string; detail: string; actions?: React.ReactNode }) {
  return (
    <div className="reliability-v2__section-heading reliability-v2__section-heading--page">
      <div>
        <p className="reliability-v2__eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
      {actions && <div className="reliability-v2__actions">{actions}</div>}
    </div>
  );
}

function RequestState({ loading, error }: { loading: boolean; error: string | null }) {
  if (loading) return <div className="reliability-v2__loading" role="status">Loading controlled Reliability records…</div>;
  if (error) return <div className="reliability-v2__error" role="alert">{error}</div>;
  return null;
}

function PermissionNote({ capability, snapshot }: { capability: string; snapshot: ReliabilityCapabilitySnapshot }) {
  if (hasCapability(snapshot, capability)) return null;
  return <p className="reliability-v2__permission-note">Read only. Required capability: <code>{capability}</code>.</p>;
}

function JsonDisclosure({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="reliability-v2__json">
      <summary>{label}</summary>
      <pre>{jsonText(value)}</pre>
    </details>
  );
}

export function ReliabilityAdvancedView({
  view,
  basePath,
}: {
  view: AdvancedReliabilityViewId;
  basePath: string;
}): React.ReactElement {
  if (view === "compliance") return <ComplianceView basePath={basePath} />;
  if (view === "sources" || view === "ingestion") return <SourcesView />;
  if (view === "data-quality") return <DataQualityView />;
  if (view === "fleet") return <AnalyticsView scopeType="AIRCRAFT" />;
  if (view === "systems") return <AnalyticsView scopeType="ATA" />;
  if (view === "components") return <AnalyticsView scopeType="COMPONENT" />;
  if (view === "calculations") return <CalculationsView />;
  if (view === "program") return <ProgrammeView />;
  if (view === "changes") return <ChangesView />;
  if (view === "handoffs") return <HandoffsView />;
  if (view === "meetings") return <MeetingsView />;
  if (view === "authority") return <AuthorityView />;
  return <AiView />;
}

function ComplianceView({ basePath }: { basePath: string }) {
  const resource = useResource<ReliabilityCompliance>(() => getReliabilityCompliance(), []);
  const capabilities = useReliabilityCapabilities();
  const [actionError, setActionError] = useState<string | null>(null);
  const canBootstrap = hasCapability(capabilities, "reliability.programme.manage");
  const bootstrap = async () => {
    setActionError(null);
    try {
      await bootstrapReliability();
      resource.refresh();
    } catch (error) {
      setActionError(errorMessage(error));
    }
  };
  return (
    <section className="reliability-v2__section">
      <PageHeading
        eyebrow="Control assurance"
        title="Reliability compliance control"
        detail="Evidence-based configuration and workflow status. Green means the configured control passed; it is not an automatic regulatory declaration."
        actions={<button className="btn btn-secondary" type="button" disabled={!canBootstrap} onClick={bootstrap}>Bootstrap controlled baseline</button>}
      />
      <RequestState loading={resource.loading} error={resource.error || actionError} />
      {resource.data && (
        <>
          <div className="reliability-v2__compliance-banner">
            <span className={statusClass(resource.data.overall_status)}>{resource.data.overall_status}</span>
            <div><strong>{resource.data.regulatory_profiles.join(" · ") || "No effective regulatory profile"}</strong><p>{resource.data.disclaimer}</p></div>
          </div>
          <div className="reliability-v2__check-grid">
            {resource.data.checks.map((check) => (
              <Link to={`${basePath}/${check.route || "compliance"}`} className="reliability-v2__check" key={check.code}>
                <span className={statusClass(check.status)}>{check.status}</span>
                <strong>{check.title}</strong>
                <p>{check.detail}</p>
                {check.count != null && <small>{check.count} record(s)</small>}
              </Link>
            ))}
          </div>
        </>
      )}
      <PermissionNote capability="reliability.programme.manage" snapshot={capabilities} />
    </section>
  );
}

function SourcesView() {
  const capabilities = useReliabilityCapabilities();
  const sources = useResource<ReliabilitySource[]>(() => listReliabilitySources(), []);
  const batches = useResource<ReliabilityIngestionBatch[]>(() => listReliabilityIngestionBatches(), []);
  const [selectedSource, setSelectedSource] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const runAction = async (action: () => Promise<unknown>) => {
    setMessage(null);
    setActionError(null);
    try {
      await action();
      setMessage("Reliability source operation completed.");
      sources.refresh();
      batches.refresh();
    } catch (error) {
      setActionError(errorMessage(error));
    }
  };

  const submitSource = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void runAction(() => createReliabilitySource({
      code: String(data.get("code") || ""),
      name: String(data.get("name") || ""),
      source_type: String(data.get("source_type") || "TECH_LOG"),
      transport: String(data.get("transport") || "PUSH"),
      mapping_version: String(data.get("mapping_version") || "1"),
      poll_interval_minutes: data.get("poll_interval_minutes") ? Number(data.get("poll_interval_minutes")) : null,
      configuration_json: parseJson(data.get("configuration_json"), {}),
    }));
  };

  const submitBatch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    let records: Array<Record<string, unknown>>;
    try {
      const parsed = parseJson(data.get("records"), []);
      records = Array.isArray(parsed) ? parsed as Array<Record<string, unknown>> : [parsed as Record<string, unknown>];
    } catch (error) {
      setActionError(`Invalid JSON: ${errorMessage(error)}`);
      return;
    }
    if (!selectedSource) {
      setActionError("Select a source before ingesting a batch.");
      return;
    }
    void runAction(() => ingestReliabilitySource(selectedSource, records, { submitted_from: "reliability-ui" }));
  };

  return (
    <>
      <section className="reliability-v2__section">
        <PageHeading
          eyebrow="Source control"
          title="Automated Reliability ingestion"
          detail="Register authoritative sources, retain immutable raw records, validate canonical occurrences and expose failed records instead of hiding them."
          actions={<button className="btn btn-secondary" type="button" disabled={!hasCapability(capabilities, "reliability.ingest")} onClick={() => void runAction(() => harvestInternalReliabilitySources())}>Harvest internal sources</button>}
        />
        <RequestState loading={sources.loading || batches.loading} error={sources.error || batches.error || actionError} />
        {message && <div className="reliability-v2__success">{message}</div>}
        <div className="reliability-v2__split reliability-v2__split--forms">
          <form className="reliability-v2__form" onSubmit={submitSource}>
            <h3>Register source</h3>
            <div className="reliability-v2__form-grid">
              <label>Code<input name="code" required placeholder="OPS-PUSH" /></label>
              <label>Name<input name="name" required placeholder="Flight operations interruptions" /></label>
              <label>Source type<select name="source_type" defaultValue="FLIGHT_OPERATIONS"><option>TECH_LOG</option><option>FLIGHT_OPERATIONS</option><option>MEL_CDL</option><option>MAINTENANCE</option><option>TECH_RECORDS</option><option>COMPONENT_SHOP</option><option>EHM</option><option>QMS</option><option>SMS</option><option>PROCUREMENT</option><option>MANUAL</option></select></label>
              <label>Transport<select name="transport" defaultValue="PUSH"><option>PUSH</option><option>POLL</option><option>INTERNAL</option></select></label>
              <label>Mapping version<input name="mapping_version" defaultValue="1" /></label>
              <label>Poll interval (minutes)<input type="number" name="poll_interval_minutes" min="5" /></label>
            </div>
            <label>Configuration JSON<textarea name="configuration_json" rows={4} defaultValue={'{"canonical_contract":"reliability-event-v1"}'} /></label>
            <button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.source.manage")}>Create source</button>
            <PermissionNote capability="reliability.source.manage" snapshot={capabilities} />
          </form>
          <form className="reliability-v2__form" onSubmit={submitBatch}>
            <h3>Ingest source records</h3>
            <label>Source<select value={selectedSource} onChange={(event) => setSelectedSource(event.target.value)} required><option value="">Select source</option>{(sources.data || []).map((source) => <option value={source.id} key={source.id}>{source.code} · {source.name}</option>)}</select></label>
            <label>Canonical JSON records<textarea name="records" rows={13} defaultValue={jsonText([{ external_id: "OPS-001", event_type: "TECHNICAL_DELAY", occurred_at: new Date().toISOString(), aircraft_serial_number: "", flight_number: "", delay_minutes: 0, description: "" }])} /></label>
            <button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.ingest")}>Validate and ingest</button>
            <PermissionNote capability="reliability.ingest" snapshot={capabilities} />
          </form>
        </div>
      </section>
      <section className="reliability-v2__section">
        <PageHeading eyebrow="Source health" title="Registered inputs" detail="A source is not considered healthy until it has successfully delivered current data." />
        <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Source</th><th>Type</th><th>Transport</th><th>Status</th><th>Last success</th><th>Last failure</th></tr></thead><tbody>
          {(sources.data || []).map((source) => <tr key={source.id}><td><strong>{source.code}</strong><small>{source.name}</small></td><td>{source.source_type}</td><td>{source.transport}</td><td><span className={statusClass(source.status)}>{source.status}</span></td><td>{displayDate(source.last_success_at)}</td><td>{displayDate(source.last_failure_at)}</td></tr>)}
          {!sources.data?.length && <tr><td colSpan={6}>No Reliability sources have been registered.</td></tr>}
        </tbody></table></div>
      </section>
      <section className="reliability-v2__section">
        <PageHeading eyebrow="Immutable intake" title="Ingestion batches" detail="Every delivery records valid, duplicate and rejected counts with a content hash." />
        <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Received</th><th>Source</th><th>Status</th><th>Records</th><th>Valid</th><th>Duplicates</th><th>Rejected</th><th>Hash</th></tr></thead><tbody>
          {(batches.data || []).map((batch) => <tr key={batch.id}><td>{displayDate(batch.received_at)}</td><td>{batch.source_id}</td><td><span className={statusClass(batch.status)}>{batch.status}</span></td><td>{batch.record_count}</td><td>{batch.valid_count}</td><td>{batch.duplicate_count}</td><td>{batch.invalid_count}</td><td><code>{batch.content_hash.slice(0, 12)}</code></td></tr>)}
          {!batches.data?.length && <tr><td colSpan={8}>No ingestion batches are available.</td></tr>}
        </tbody></table></div>
      </section>
    </>
  );
}

function DataQualityView() {
  const capabilities = useReliabilityCapabilities();
  const resource = useResource<ReliabilityDataQualityIssue[]>(() => listReliabilityDataQualityIssues(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const resolve = async (issue: ReliabilityDataQualityIssue, status: "RESOLVED" | "WAIVED") => {
    const resolution = window.prompt(`${status === "WAIVED" ? "Waiver justification" : "Resolution evidence"} for ${issue.issue_code}`);
    if (!resolution) return;
    setActionError(null);
    try {
      await resolveReliabilityDataQualityIssue(issue.id, resolution, status);
      resource.refresh();
    } catch (error) {
      setActionError(errorMessage(error));
    }
  };
  return (
    <section className="reliability-v2__section">
      <PageHeading eyebrow="No data, no green" title="Data-quality exception register" detail="Invalid, stale and incomplete evidence remains visible until resolved or formally waived with accountable justification." />
      <RequestState loading={resource.loading} error={resource.error || actionError} />
      <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Raised</th><th>Severity</th><th>Code</th><th>Message</th><th>Status</th><th>Resolution</th><th>Action</th></tr></thead><tbody>
        {(resource.data || []).map((issue) => <tr key={issue.id}><td>{displayDate(issue.created_at)}</td><td><span className={statusClass(issue.severity)}>{issue.severity}</span></td><td>{issue.issue_code}</td><td>{issue.message}<JsonDisclosure label="Details" value={issue.details_json} /></td><td><span className={statusClass(issue.status)}>{issue.status}</span></td><td>{issue.resolution || "—"}</td><td><div className="reliability-v2__actions"><button className="btn btn-small" type="button" disabled={issue.status !== "OPEN" || !hasCapability(capabilities, "reliability.data_quality.resolve")} onClick={() => void resolve(issue, "RESOLVED")}>Resolve</button><button className="btn btn-small btn-secondary" type="button" disabled={issue.status !== "OPEN" || !hasCapability(capabilities, "reliability.data_quality.resolve")} onClick={() => void resolve(issue, "WAIVED")}>Waive</button></div></td></tr>)}
        {!resource.data?.length && <tr><td colSpan={7}>No data-quality exceptions are open.</td></tr>}
      </tbody></table></div>
      <PermissionNote capability="reliability.data_quality.resolve" snapshot={capabilities} />
    </section>
  );
}

function AnalyticsView({ scopeType }: { scopeType: "AIRCRAFT" | "ATA" | "COMPONENT" }) {
  const [periodStart, setPeriodStart] = useState(today(-90));
  const [periodEnd, setPeriodEnd] = useState(today());
  const [denominatorType, setDenominatorType] = useState("FH");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const loader = useCallback(() => getReliabilityAnalytics({
    scopeType,
    periodStart,
    periodEnd,
    denominatorType,
    multiplier: denominatorType === "FH" ? 100 : 100,
    eventTypes: selectedEvents,
  }), [denominatorType, periodEnd, periodStart, scopeType, selectedEvents]);
  const resource = useResource<ReliabilityAnalytics>(loader, [loader]);
  const title = scopeType === "AIRCRAFT" ? "Aircraft and fleet reliability" : scopeType === "ATA" ? "ATA system intelligence" : "Component reliability";
  return (
    <section className="reliability-v2__section">
      <PageHeading eyebrow="Exposure-aware analysis" title={title} detail="Rates show their denominator, confidence interval and small-fleet warning. Missing exposure never becomes a green result." />
      <div className="reliability-v2__toolbar">
        <label>From<input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
        <label>To<input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
        <label>Exposure<select value={denominatorType} onChange={(event) => setDenominatorType(event.target.value)}><option value="FH">Flight hours</option><option value="FC">Flight cycles</option><option value="FLIGHTS">Flights</option><option value="DAYS">Calendar days</option><option value="POPULATION">Population</option></select></label>
        <label>Occurrence filter<select multiple value={selectedEvents} onChange={(event) => setSelectedEvents(Array.from(event.target.selectedOptions, (option) => option.value))}>{EVENT_TYPES.map((eventType) => <option key={eventType}>{eventType}</option>)}</select></label>
        <button className="btn btn-secondary" type="button" onClick={resource.refresh}>Recalculate view</button>
      </div>
      <RequestState loading={resource.loading} error={resource.error} />
      {resource.data && <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>{scopeType}</th><th>Occurrences</th><th>Exposure</th><th>Rate</th><th>95% confidence</th><th>Fleet basis</th><th>Status</th><th>Detail</th></tr></thead><tbody>
        {resource.data.rows.map((row) => <tr key={row.scope_id}><td><strong>{row.label}</strong></td><td>{row.events}</td><td>{row.exposure} {resource.data?.denominator_type}</td><td>{row.rate ?? "—"}</td><td>{row.confidence_lower ?? "—"} – {row.confidence_upper ?? "—"}</td><td>{row.small_fleet ? <span className={statusClass("AMBER")}>Small fleet</span> : "Standard"}</td><td><span className={statusClass(row.status)}>{row.status.replaceAll("_", " ")}</span></td><td><JsonDisclosure label="Evidence" value={row.details} /></td></tr>)}
        {!resource.data.rows.length && <tr><td colSpan={8}>No scoped Reliability evidence is available for this period.</td></tr>}
      </tbody></table></div>}
    </section>
  );
}

function CalculationsView() {
  const capabilities = useReliabilityCapabilities();
  const metrics = useResource<ReliabilityMetricDefinition[]>(() => listReliabilityMetricDefinitions(), []);
  const runs = useResource<ReliabilityCalculationRun[]>(() => listReliabilityCalculationRuns(), []);
  const [metricId, setMetricId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const execute = async (due: boolean) => {
    setActionError(null);
    try {
      if (due) await runDueReliabilityCalculations();
      else if (metricId) await executeReliabilityCalculation({ metric_definition_id: metricId });
      else throw new Error("Select a metric definition.");
      runs.refresh();
      metrics.refresh();
    } catch (error) {
      setActionError(errorMessage(error));
    }
  };
  return (
    <section className="reliability-v2__section">
      <PageHeading eyebrow="Retained calculation evidence" title="Scheduled KPI calculation runs" detail="Each result retains formula version, source cutoff, lineage, confidence interval, threshold result and a deterministic result hash." />
      <div className="reliability-v2__toolbar">
        <label>Metric<select value={metricId} onChange={(event) => setMetricId(event.target.value)}><option value="">Select metric</option>{(metrics.data || []).map((metric) => <option value={metric.id} key={metric.id}>{metric.code} · {metric.name}</option>)}</select></label>
        <button className="btn btn-primary" type="button" disabled={!hasCapability(capabilities, "reliability.metric.execute")} onClick={() => void execute(false)}>Run selected</button>
        <button className="btn btn-secondary" type="button" disabled={!hasCapability(capabilities, "reliability.metric.execute")} onClick={() => void execute(true)}>Run all due</button>
      </div>
      <RequestState loading={metrics.loading || runs.loading} error={metrics.error || runs.error || actionError} />
      <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Period</th><th>Metric</th><th>Scope</th><th>Numerator</th><th>Exposure</th><th>Value</th><th>Confidence</th><th>Status</th><th>Evidence</th></tr></thead><tbody>
        {(runs.data || []).map((run) => <tr key={run.id}><td>{run.period_start} – {run.period_end}</td><td>{run.metric_definition_id}</td><td>{run.scope_type}: {run.scope_id}</td><td>{run.numerator ?? "—"}</td><td>{run.denominator ?? "—"}</td><td>{run.value ?? "—"}</td><td>{run.confidence_lower ?? "—"} – {run.confidence_upper ?? "—"}</td><td><span className={statusClass(run.status)}>{run.status}</span>{run.small_fleet && <small>Small fleet</small>}</td><td><code>{run.result_hash.slice(0, 12)}</code><JsonDisclosure label="Lineage" value={run.source_lineage_json} /></td></tr>)}
        {!runs.data?.length && <tr><td colSpan={9}>No governed calculation runs are available.</td></tr>}
      </tbody></table></div>
      <PermissionNote capability="reliability.metric.execute" snapshot={capabilities} />
    </section>
  );
}

function ProgrammeView() {
  const capabilities = useReliabilityCapabilities();
  const programmes = useResource<ReliabilityProgramme[]>(() => listReliabilityProgrammes(), []);
  const versions = useResource<ReliabilityProgrammeVersion[]>(() => listReliabilityProgrammeVersions(), []);
  const metrics = useResource<ReliabilityMetricDefinition[]>(() => listReliabilityMetricDefinitions(), []);
  const thresholds = useResource<ReliabilityThresholdVersion[]>(() => listReliabilityThresholdVersions(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedProgramme, setSelectedProgramme] = useState("");
  const [selectedVersion, setSelectedVersion] = useState("");
  const [selectedMetric, setSelectedMetric] = useState("");

  const refresh = () => { programmes.refresh(); versions.refresh(); metrics.refresh(); thresholds.refresh(); };
  const action = async (operation: () => Promise<unknown>) => {
    setActionError(null);
    try { await operation(); refresh(); } catch (error) { setActionError(errorMessage(error)); }
  };
  const createProgramme = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void action(() => createReliabilityProgramme({ code: data.get("code"), name: data.get("name"), description: data.get("description") }));
  };
  const createVersion = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    if (!selectedProgramme) { setActionError("Select a programme."); return; }
    try {
      void action(() => createReliabilityProgrammeVersion(selectedProgramme, {
        revision: data.get("revision"), change_summary: data.get("change_summary"),
        regulatory_profiles: Array.from(data.getAll("profiles"), String),
        scope_json: parseJson(data.get("scope_json"), {}),
        data_sources_json: parseJson(data.get("data_sources_json"), []),
        reporting_json: parseJson(data.get("reporting_json"), {}),
        responsibility_matrix_json: parseJson(data.get("responsibility_matrix_json"), {}),
        authority_required: data.get("authority_required") === "on",
      }));
    } catch (error) { setActionError(`Invalid JSON: ${errorMessage(error)}`); }
  };
  const createMetric = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    if (!selectedVersion) { setActionError("Select a programme version."); return; }
    void action(() => createReliabilityMetricDefinition(selectedVersion, {
      code: data.get("code"), name: data.get("name"), scope_type: data.get("scope_type"), method: "RATE",
      numerator_event_types: String(data.get("numerator_event_types") || "").split(",").map((item) => item.trim()).filter(Boolean),
      denominator_type: data.get("denominator_type"), multiplier: Number(data.get("multiplier") || 100),
      window_days: Number(data.get("window_days") || 30), schedule_interval_minutes: Number(data.get("schedule_interval_minutes") || 1440),
      minimum_exposure: Number(data.get("minimum_exposure") || 1), direction: "ABOVE", formula_version: data.get("formula_version") || "1",
    }));
  };
  const createThreshold = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    if (!selectedMetric) { setActionError("Select a metric definition."); return; }
    void action(() => createReliabilityThresholdVersion(selectedMetric, {
      version: data.get("version"), caution_value: Number(data.get("caution_value")), alert_value: Number(data.get("alert_value")),
      minimum_exposure: Number(data.get("minimum_exposure")), rationale: data.get("rationale"),
    }));
  };
  return (
    <>
      <section className="reliability-v2__section">
        <PageHeading eyebrow="Controlled programme" title="Reliability programme governance" detail="Regulatory profile, responsibility boundaries, source declarations, formulas and thresholds are versioned and approved before becoming effective." actions={<button className="btn btn-secondary" disabled={!hasCapability(capabilities, "reliability.programme.manage")} onClick={() => void action(() => bootstrapReliability())}>Bootstrap baseline</button>} />
        <RequestState loading={programmes.loading || versions.loading || metrics.loading || thresholds.loading} error={programmes.error || versions.error || metrics.error || thresholds.error || actionError} />
        <div className="reliability-v2__workflow-columns">
          <form className="reliability-v2__form" onSubmit={createProgramme}><h3>1. Programme</h3><label>Code<input name="code" required placeholder="RP-001" /></label><label>Name<input name="name" required /></label><label>Description<textarea name="description" rows={3} /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.programme.manage")}>Create</button></form>
          <form className="reliability-v2__form" onSubmit={createVersion}><h3>2. Version</h3><label>Programme<select value={selectedProgramme} onChange={(event) => setSelectedProgramme(event.target.value)} required><option value="">Select</option>{(programmes.data || []).map((item) => <option value={item.id} key={item.id}>{item.code} · {item.name}</option>)}</select></label><label>Revision<input name="revision" required defaultValue="A" /></label><label>Change summary<textarea name="change_summary" required rows={2} /></label><fieldset><legend>Profiles</legend>{["EASA_CAMO", "EASA_PART145_PROVIDER", "FAA_CASS", "FAA_PART145", "ICAO"].map((profile) => <label className="reliability-v2__check-label" key={profile}><input type="checkbox" name="profiles" value={profile} defaultChecked={["EASA_CAMO", "EASA_PART145_PROVIDER", "FAA_CASS", "ICAO"].includes(profile)} />{profile}</label>)}</fieldset><label>Scope JSON<textarea name="scope_json" rows={3} defaultValue={'{"fleet":"ALL_ACTIVE"}'} /></label><label>Sources JSON<textarea name="data_sources_json" rows={3} defaultValue={'[{"type":"TECH_LOG","required":true},{"type":"FLIGHT_OPERATIONS","required":true}]'} /></label><label>Reporting JSON<textarea name="reporting_json" rows={3} defaultValue={'{"monthly_review":true,"annual_programme_review":true}'} /></label><label>Responsibility matrix<textarea name="responsibility_matrix_json" rows={5} defaultValue={'{"programme_owner":"CAMO_OR_CERTIFICATE_HOLDER","analysis_provider":"AMO_RELIABILITY_FUNCTION","decision_authority":"CAMO_OR_CERTIFICATE_HOLDER"}'} /></label><label className="reliability-v2__check-label"><input type="checkbox" name="authority_required" />Authority acceptance required</label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.programme.manage")}>Create version</button></form>
          <form className="reliability-v2__form" onSubmit={createMetric}><h3>3. Metric</h3><label>Programme version<select value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)} required><option value="">Select</option>{(versions.data || []).map((item) => <option value={item.id} key={item.id}>{item.revision} · {item.status}</option>)}</select></label><label>Code<input name="code" required placeholder="DEFECT_RATE_100FH" /></label><label>Name<input name="name" required /></label><label>Scope<select name="scope_type"><option>FLEET</option><option>AIRCRAFT</option><option>ATA</option><option>COMPONENT</option><option>ENGINE</option></select></label><label>Numerator events<input name="numerator_event_types" placeholder="DEFECT,REPEAT_DEFECT" /></label><label>Denominator<select name="denominator_type"><option>FH</option><option>FC</option><option>FLIGHTS</option><option>DAYS</option><option>POPULATION</option><option>NONE</option></select></label><div className="reliability-v2__form-grid"><label>Multiplier<input type="number" name="multiplier" defaultValue="100" /></label><label>Window days<input type="number" name="window_days" defaultValue="30" /></label><label>Schedule minutes<input type="number" name="schedule_interval_minutes" defaultValue="1440" /></label><label>Minimum exposure<input type="number" name="minimum_exposure" defaultValue="1" /></label><label>Formula version<input name="formula_version" defaultValue="1" /></label></div><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.metric.manage")}>Create metric</button></form>
          <form className="reliability-v2__form" onSubmit={createThreshold}><h3>4. Threshold</h3><label>Metric<select value={selectedMetric} onChange={(event) => setSelectedMetric(event.target.value)} required><option value="">Select</option>{(metrics.data || []).map((item) => <option value={item.id} key={item.id}>{item.code}</option>)}</select></label><label>Version<input name="version" required defaultValue="A" /></label><div className="reliability-v2__form-grid"><label>Caution<input type="number" step="any" name="caution_value" required /></label><label>Alert<input type="number" step="any" name="alert_value" required /></label><label>Minimum exposure<input type="number" step="any" name="minimum_exposure" required /></label></div><label>Engineering rationale<textarea name="rationale" required rows={4} /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.metric.manage")}>Create threshold</button></form>
        </div>
      </section>
      <section className="reliability-v2__section"><PageHeading eyebrow="Approval control" title="Programme versions" detail="The same individual cannot bypass capability gates; authority-dependent versions cannot become effective without accepted authority evidence." /><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Revision</th><th>Profiles</th><th>Status</th><th>Responsibility</th><th>Approval</th><th>Transition</th></tr></thead><tbody>{(versions.data || []).map((version) => <tr key={version.id}><td>{version.revision}</td><td>{version.regulatory_profiles.join(", ")}</td><td><span className={statusClass(version.status)}>{version.status}</span></td><td><JsonDisclosure label="Matrix" value={version.responsibility_matrix_json} /></td><td>{version.approved_by_user_id || "—"}<small>{displayDate(version.approved_at)}</small></td><td><div className="reliability-v2__actions">{["IN_REVIEW", "APPROVED", "EFFECTIVE", "SUPERSEDED", "REJECTED"].map((next) => <button className="btn btn-small" type="button" key={next} disabled={!hasCapability(capabilities, next === "IN_REVIEW" || next === "REJECTED" ? "reliability.programme.manage" : "reliability.programme.approve")} onClick={() => { const rationale = window.prompt(`Rationale for ${next}`); if (rationale) void action(() => transitionReliabilityProgrammeVersion(version.id, next, rationale)); }}>{next}</button>)}</div></td></tr>)}</tbody></table></div></section>
      <section className="reliability-v2__section"><PageHeading eyebrow="Threshold control" title="Metric and threshold register" detail="Draft thresholds remain visibly inactive until approved and made effective." /><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Metric</th><th>Formula</th><th>Exposure</th><th>Schedule</th><th>Thresholds</th></tr></thead><tbody>{(metrics.data || []).map((metric) => <tr key={metric.id}><td><strong>{metric.code}</strong><small>{metric.name}</small></td><td>{metric.numerator_event_types.join(" + ")} / {metric.denominator_type} × {metric.multiplier}<small>v{metric.formula_version}</small></td><td>Minimum {metric.minimum_exposure}</td><td>{metric.schedule_interval_minutes} minutes<small>Next {displayDate(metric.next_run_at)}</small></td><td>{(thresholds.data || []).filter((threshold) => threshold.metric_definition_id === metric.id).map((threshold) => <div className="reliability-v2__inline-record" key={threshold.id}><span className={statusClass(threshold.status)}>{threshold.status}</span><span>C {threshold.caution_value ?? "—"} / A {threshold.alert_value ?? "—"}</span>{["APPROVED", "EFFECTIVE", "SUPERSEDED", "REJECTED"].map((next) => <button className="btn btn-small" type="button" key={next} disabled={!hasCapability(capabilities, "reliability.programme.approve")} onClick={() => { const rationale = window.prompt(`Threshold ${next} rationale`); if (rationale) void action(() => transitionReliabilityThresholdVersion(threshold.id, next, rationale)); }}>{next}</button>)}</div>)}</td></tr>)}</tbody></table></div></section>
    </>
  );
}

function ChangesView() {
  const capabilities = useReliabilityCapabilities();
  const resource = useResource<ReliabilityChangeProposal[]>(() => listReliabilityChanges(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const action = async (operation: () => Promise<unknown>) => { setActionError(null); try { await operation(); resource.refresh(); } catch (error) { setActionError(errorMessage(error)); } };
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    try { void action(() => createReliabilityChange({ source_type: data.get("source_type"), source_id: data.get("source_id"), proposal_type: data.get("proposal_type"), title: data.get("title"), problem_statement: data.get("problem_statement"), proposed_change_json: parseJson(data.get("proposed_change_json"), {}), impact_assessment_json: parseJson(data.get("impact_assessment_json"), {}) })); } catch (error) { setActionError(`Invalid JSON: ${errorMessage(error)}`); }
  };
  return <section className="reliability-v2__section"><PageHeading eyebrow="Decision to execution" title="Controlled change proposals" detail="Reliability findings become governed AMP, interval, procedure, supplier or maintenance changes with simulation, approvals and effectiveness dates." /><RequestState loading={resource.loading} error={resource.error || actionError} /><form className="reliability-v2__form reliability-v2__form--horizontal" onSubmit={submit}><label>Source type<input name="source_type" required placeholder="FRACAS_CASE" /></label><label>Source ID<input name="source_id" required /></label><label>Proposal type<select name="proposal_type"><option>AMP_TASK</option><option>INTERVAL</option><option>THRESHOLD</option><option>PROCEDURE</option><option>SUPPLIER</option><option>MAINTENANCE</option><option>OTHER</option></select></label><label>Title<input name="title" required /></label><label>Problem statement<textarea name="problem_statement" required rows={3} /></label><label>Proposed change JSON<textarea name="proposed_change_json" rows={4} defaultValue="{}" /></label><label>Impact assessment JSON<textarea name="impact_assessment_json" rows={4} defaultValue="{}" /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.change.manage")}>Create proposal</button></form><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Proposal</th><th>Source</th><th>Status</th><th>Impact</th><th>Simulation</th><th>Control</th></tr></thead><tbody>{(resource.data || []).map((proposal) => <tr key={proposal.id}><td><strong>{proposal.title}</strong><small>{proposal.proposal_type}</small><p>{proposal.problem_statement}</p></td><td>{proposal.source_type}: {proposal.source_id}</td><td><span className={statusClass(proposal.status)}>{proposal.status}</span></td><td><JsonDisclosure label="Assessment" value={proposal.impact_assessment_json} /></td><td><JsonDisclosure label="Simulation" value={proposal.simulation_json} /></td><td><div className="reliability-v2__actions"><button className="btn btn-small" type="button" disabled={!hasCapability(capabilities, "reliability.change.manage")} onClick={() => void action(() => simulateReliabilityChange(proposal.id, { annual_utilisation_hours: 1200, fleet_size: 1, current_interval: 500, proposed_interval: 600, average_manhours: 6, average_material_cost: 500 }))}>Simulate</button>{["TECH_REVIEW", "QUALITY_REVIEW", "APPROVED", "AUTHORITY_REVIEW", "IMPLEMENTED", "CLOSED", "REJECTED"].map((next) => <button className="btn btn-small" type="button" key={next} disabled={!hasCapability(capabilities, ["APPROVED", "AUTHORITY_REVIEW", "IMPLEMENTED", "CLOSED"].includes(next) ? "reliability.change.approve" : "reliability.change.manage")} onClick={() => { const rationale = window.prompt(`${next} rationale`); if (rationale) void action(() => transitionReliabilityChange(proposal.id, { to_status: next, rationale })); }}>{next}</button>)}</div></td></tr>)}</tbody></table></div></section>;
}

function HandoffsView() {
  const capabilities = useReliabilityCapabilities();
  const resource = useResource<ReliabilityHandoff[]>(() => listReliabilityHandoffs(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const action = async (operation: () => Promise<unknown>) => { setActionError(null); try { await operation(); resource.refresh(); } catch (error) { setActionError(errorMessage(error)); } };
  const submit = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { void action(() => createReliabilityHandoff({ source_type: data.get("source_type"), source_id: data.get("source_id"), target_module: data.get("target_module"), target_route: data.get("target_route") || null, payload_json: parseJson(data.get("payload_json"), {}) })); } catch (error) { setActionError(`Invalid JSON: ${errorMessage(error)}`); } };
  return <section className="reliability-v2__section"><PageHeading eyebrow="Closed-loop implementation" title="Cross-module handoffs" detail="Approved Reliability action creates an accountable task and remains open until the target module acknowledges and completes its authoritative record." /><RequestState loading={resource.loading} error={resource.error || actionError} /><form className="reliability-v2__form reliability-v2__form--horizontal" onSubmit={submit}><label>Source type<input name="source_type" required placeholder="CHANGE_PROPOSAL" /></label><label>Source ID<input name="source_id" required /></label><label>Target module<select name="target_module"><option>PLANNING</option><option>MAINTENANCE</option><option>TECH_RECORDS</option><option>QMS</option><option>SMS</option><option>PROCUREMENT</option></select></label><label>Target route<input name="target_route" placeholder="/maintenance/..." /></label><label>Payload JSON<textarea name="payload_json" rows={5} defaultValue={'{"summary":"Implement approved Reliability action","priority":2}'} /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.handoff.manage")}>Create handoff</button></form><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Created</th><th>Source</th><th>Target</th><th>Status</th><th>Task</th><th>Authoritative record</th><th>Control</th></tr></thead><tbody>{(resource.data || []).map((handoff) => <tr key={handoff.id}><td>{displayDate(handoff.created_at)}</td><td>{handoff.source_type}: {handoff.source_id}</td><td>{handoff.target_module}<small>{handoff.target_route}</small></td><td><span className={statusClass(handoff.status)}>{handoff.status}</span></td><td>{handoff.task_id || "Not sent"}</td><td>{handoff.target_record_type ? `${handoff.target_record_type}: ${handoff.target_record_id}` : "—"}</td><td><div className="reliability-v2__actions">{["SENT", "ACKNOWLEDGED", "COMPLETED", "REJECTED", "CANCELLED"].map((next) => <button className="btn btn-small" type="button" key={next} disabled={!hasCapability(capabilities, "reliability.handoff.manage")} onClick={() => { const rationale = window.prompt(`${next} evidence or rationale`); if (rationale) void action(() => transitionReliabilityHandoff(handoff.id, { to_status: next, rationale, target_record_type: next === "COMPLETED" ? window.prompt("Target record type") : undefined, target_record_id: next === "COMPLETED" ? window.prompt("Target record ID") : undefined })); }}>{next}</button>)}</div></td></tr>)}</tbody></table></div></section>;
}

function MeetingsView() {
  const capabilities = useReliabilityCapabilities();
  const resource = useResource<ReliabilityMeeting[]>(() => listReliabilityMeetings(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const action = async (operation: () => Promise<unknown>) => { setActionError(null); try { await operation(); resource.refresh(); } catch (error) { setActionError(errorMessage(error)); } };
  const submit = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { void action(() => createReliabilityMeeting({ title: data.get("title"), scheduled_at: new Date(String(data.get("scheduled_at"))).toISOString(), meeting_type: data.get("meeting_type"), agenda_json: parseJson(data.get("agenda_json"), []), attendees_json: parseJson(data.get("attendees_json"), []), quorum_json: parseJson(data.get("quorum_json"), {}) })); } catch (error) { setActionError(`Invalid meeting input: ${errorMessage(error)}`); } };
  return <section className="reliability-v2__section"><PageHeading eyebrow="Controlled review board" title="Reliability meetings and decisions" detail="A meeting freezes its data cutoff, records quorum, minutes, decisions, dissent and assigned actions before approval." /><RequestState loading={resource.loading} error={resource.error || actionError} /><form className="reliability-v2__form reliability-v2__form--horizontal" onSubmit={submit}><label>Title<input name="title" required placeholder="Monthly Fleet Reliability Review" /></label><label>Type<select name="meeting_type"><option>MONTHLY_RELIABILITY</option><option>PROGRAMME_REVIEW</option><option>ETOPS_REVIEW</option><option>AD_HOC_TECHNICAL</option></select></label><label>Scheduled<input type="datetime-local" name="scheduled_at" required defaultValue={localDateTime(24)} /></label><label>Agenda JSON<textarea name="agenda_json" rows={4} defaultValue={'[{"topic":"Data quality"},{"topic":"Alerts and FRACAS"},{"topic":"Programme changes"}]'} /></label><label>Attendees JSON<textarea name="attendees_json" rows={4} defaultValue="[]" /></label><label>Quorum JSON<textarea name="quorum_json" rows={4} defaultValue={'{"required_roles":["PROGRAMME_OWNER","RELIABILITY_MANAGER","QUALITY"]}'} /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.meeting.manage")}>Schedule meeting</button></form><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Meeting</th><th>Schedule</th><th>Status</th><th>Data cut</th><th>Records</th><th>Control</th></tr></thead><tbody>{(resource.data || []).map((meeting) => <tr key={meeting.id}><td><strong>{meeting.title}</strong><small>{meeting.meeting_type}</small></td><td>{displayDate(meeting.scheduled_at)}</td><td><span className={statusClass(meeting.status)}>{meeting.status}</span></td><td>{displayDate(meeting.data_cutoff_at)}</td><td><JsonDisclosure label="Agenda" value={meeting.agenda_json} /><JsonDisclosure label="Attendees" value={meeting.attendees_json} /><JsonDisclosure label="Quorum" value={meeting.quorum_json} />{meeting.minutes && <details><summary>Approved minutes</summary><p>{meeting.minutes}</p></details>}</td><td><div className="reliability-v2__actions">{["AGENDA_LOCKED", "HELD", "APPROVED", "CLOSED", "CANCELLED"].map((next) => <button className="btn btn-small" type="button" key={next} disabled={!hasCapability(capabilities, "reliability.meeting.manage")} onClick={() => { const rationale = window.prompt(`${next} rationale`); if (!rationale) return; const minutes = next === "APPROVED" ? window.prompt("Controlled meeting minutes") : undefined; void action(() => transitionReliabilityMeeting(meeting.id, { to_status: next, rationale, minutes })); }}>{next}</button>)}<button className="btn btn-small btn-secondary" type="button" disabled={!hasCapability(capabilities, "reliability.meeting.manage")} onClick={() => { const title = window.prompt("Decision title"); const decision = window.prompt("Decision"); const rationale = window.prompt("Technical rationale"); if (title && decision && rationale) void action(() => createReliabilityMeetingDecision(meeting.id, { decision_type: "TECHNICAL", title, decision, rationale })); }}>Add decision</button></div></td></tr>)}</tbody></table></div></section>;
}

function AuthorityView() {
  const capabilities = useReliabilityCapabilities();
  const resource = useResource<ReliabilityAuthoritySubmission[]>(() => listReliabilityAuthoritySubmissions(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const action = async (operation: () => Promise<unknown>) => { setActionError(null); try { await operation(); resource.refresh(); } catch (error) { setActionError(errorMessage(error)); } };
  const submit = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { void action(() => createReliabilityAuthoritySubmission({ programme_version_id: data.get("programme_version_id") || null, change_proposal_id: data.get("change_proposal_id") || null, meeting_id: data.get("meeting_id") || null, authority_profile: data.get("authority_profile"), submission_type: data.get("submission_type"), external_reference: data.get("external_reference") || null, package_manifest_json: parseJson(data.get("package_manifest_json"), {}) })); } catch (error) { setActionError(`Invalid package JSON: ${errorMessage(error)}`); } };
  return <section className="reliability-v2__section"><PageHeading eyebrow="Authority boundary" title="Controlled authority submissions" detail="The portal prepares and records authority packages; submission requires a separate capability and never occurs from AI output or an unapproved programme change." /><RequestState loading={resource.loading} error={resource.error || actionError} /><form className="reliability-v2__form reliability-v2__form--horizontal" onSubmit={submit}><label>Authority<select name="authority_profile"><option>EASA</option><option>FAA</option><option>KCAA</option><option>ICAO</option><option>OTHER</option></select></label><label>Submission type<input name="submission_type" required placeholder="PROGRAMME_CHANGE" /></label><label>Programme version<input name="programme_version_id" /></label><label>Change proposal<input name="change_proposal_id" /></label><label>Meeting<input name="meeting_id" /></label><label>External reference<input name="external_reference" /></label><label>Package manifest JSON<textarea name="package_manifest_json" rows={8} defaultValue={jsonText({ source_cutoff_at: new Date().toISOString(), evidence: [], responsibility_statement: "CAMO/certificate holder retains decision authority", approval_record: {} })} /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.authority.prepare")}>Prepare package</button></form><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Package</th><th>Authority</th><th>Status</th><th>Reference</th><th>Manifest</th><th>Control</th></tr></thead><tbody>{(resource.data || []).map((submission) => <tr key={submission.id}><td>{submission.submission_type}<small>{displayDate(submission.created_at)}</small></td><td>{submission.authority_profile}</td><td><span className={statusClass(submission.status)}>{submission.status}</span></td><td>{submission.external_reference || "—"}</td><td><JsonDisclosure label="Package" value={submission.package_manifest_json} /><JsonDisclosure label="Response" value={submission.response_json} /></td><td><div className="reliability-v2__actions">{["READY", "SUBMITTED", "ACKNOWLEDGED", "ACCEPTED", "REJECTED", "WITHDRAWN"].map((next) => <button className="btn btn-small" type="button" key={next} disabled={!hasCapability(capabilities, ["SUBMITTED", "ACKNOWLEDGED", "ACCEPTED", "REJECTED", "WITHDRAWN"].includes(next) ? "reliability.authority.submit" : "reliability.authority.prepare")} onClick={() => { const rationale = window.prompt(`${next} rationale`); if (rationale) void action(() => transitionReliabilityAuthoritySubmission(submission.id, { to_status: next, rationale, external_reference: next === "SUBMITTED" ? window.prompt("Authority reference") : undefined })); }}>{next}</button>)}</div></td></tr>)}</tbody></table></div></section>;
}

function AiView() {
  const capabilities = useReliabilityCapabilities();
  const resource = useResource<ReliabilityAiReview[]>(() => listReliabilityAiReviews(), []);
  const audit = useResource<ReliabilityAuditEvent[]>(() => listReliabilityAuditEvents(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const action = async (operation: () => Promise<unknown>) => { setActionError(null); try { await operation(); resource.refresh(); audit.refresh(); } catch (error) { setActionError(errorMessage(error)); } };
  const submit = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); void action(() => createReliabilityAiReview({ review_type: data.get("review_type"), entity_type: data.get("entity_type"), entity_id: data.get("entity_id"), instruction: data.get("instruction") || null })); };
  return <><section className="reliability-v2__section"><PageHeading eyebrow="Human-approved assistance" title="Explainable Reliability AI reviews" detail="AI output is advisory, versioned, cited and incapable of approving programmes, deferring defects, closing FRACAS or sending authority submissions." /><RequestState loading={resource.loading || audit.loading} error={resource.error || audit.error || actionError} /><form className="reliability-v2__form reliability-v2__form--horizontal" onSubmit={submit}><label>Review type<select name="review_type"><option>TRIAGE</option><option>REPEAT_CLUSTER</option><option>ROOT_CAUSE</option><option>REPORT_SUMMARY</option><option>EVIDENCE_GAP</option><option>CHANGE_IMPACT</option></select></label><label>Entity type<select name="entity_type"><option>FRACAS_CASE</option><option>OCCURRENCE</option><option>CHANGE_PROPOSAL</option></select></label><label>Entity ID<input name="entity_id" required /></label><label>Instruction<textarea name="instruction" rows={3} /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.ai.use")}>Generate advisory review</button></form><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Created</th><th>Review</th><th>Entity</th><th>Model</th><th>Confidence</th><th>Evidence</th><th>Output</th><th>Human decision</th></tr></thead><tbody>{(resource.data || []).map((review) => <tr key={review.id}><td>{displayDate(review.created_at)}</td><td>{review.review_type}<small><span className={statusClass(review.status)}>{review.status}</span></small></td><td>{review.entity_type}: {review.entity_id}</td><td>{review.model_id}<small>v{review.model_version}</small><code>{review.prompt_hash.slice(0, 12)}</code></td><td>{review.confidence ?? "—"}<small>{review.advisory_only ? "Advisory only" : "Invalid mode"}</small></td><td><JsonDisclosure label={`${review.citations_json.length} citation(s)`} value={review.citations_json} /></td><td><JsonDisclosure label="Review output" value={review.output_json} /></td><td>{review.review_notes || "Pending human review"}<div className="reliability-v2__actions">{["ACCEPTED", "REJECTED", "REVIEWED"].map((decision) => <button className="btn btn-small" type="button" key={decision} disabled={!hasCapability(capabilities, "reliability.ai.review") || !["DRAFT", "REVIEWED"].includes(review.status)} onClick={() => { const notes = window.prompt(`${decision} review notes`); if (notes) void action(() => transitionReliabilityAiReview(review.id, decision, notes)); }}>{decision}</button>)}</div></td></tr>)}</tbody></table></div></section><section className="reliability-v2__section"><PageHeading eyebrow="Tamper-evident evidence" title="Reliability decision ledger" detail="Each event includes the prior hash and current event hash to expose modification or deletion attempts." /><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>When</th><th>Entity</th><th>Action</th><th>Actor</th><th>Hash chain</th><th>Payload</th></tr></thead><tbody>{(audit.data || []).map((event) => <tr key={event.id}><td>{displayDate(event.created_at)}</td><td>{event.entity_type}: {event.entity_id}</td><td>{event.action}</td><td>{event.actor_user_id || "SYSTEM"}</td><td><code>{event.previous_hash?.slice(0, 10) || "GENESIS"} → {event.event_hash.slice(0, 10)}</code></td><td><JsonDisclosure label="Recorded payload" value={event.payload_json} /></td></tr>)}</tbody></table></div></section></>;
}

export function OccurrenceProvenancePanel({ eventId }: { eventId: number }) {
  const resource = useResource<OccurrenceProvenance>(() => getOccurrenceProvenance(eventId), [eventId]);
  return <section className="reliability-v2__section"><PageHeading eyebrow="Immutable provenance" title="Source evidence" detail="The normalized occurrence remains linked to the exact source, batch, external ID, payload hash, validation findings and operational-interruption detail." /><RequestState loading={resource.loading} error={resource.error} />{resource.data && <div className="reliability-v2__evidence-grid"><dl><dt>Source</dt><dd>{resource.data.source ? `${resource.data.source.code} · ${resource.data.source.name}` : "Manual / legacy record"}</dd><dt>External ID</dt><dd>{resource.data.external_id || "—"}</dd><dt>Payload hash</dt><dd><code>{resource.data.payload_hash || "—"}</code></dd><dt>Validation</dt><dd><span className={statusClass(resource.data.validation_status)}>{resource.data.validation_status || "UNKNOWN"}</span></dd></dl><JsonDisclosure label="Validation findings" value={resource.data.validation_errors} /><JsonDisclosure label="Raw source record" value={resource.data.raw_payload} /><JsonDisclosure label="Operational interruption" value={resource.data.interruption} /></div>}</section>;
}

export function FracasGovernancePanel({ caseId }: { caseId: number }) {
  const capabilities = useReliabilityCapabilities();
  const lifecycle = useResource<FracasLifecycle>(() => getFracasLifecycle(caseId), [caseId]);
  const evidence = useResource<FracasEvidence[]>(() => listFracasEvidence(caseId), [caseId]);
  const stageEvents = useResource<FracasStageEvent[]>(() => listFracasStageEvents(caseId), [caseId]);
  const reviews = useResource<EffectivenessReview[]>(() => listEffectivenessReviews(caseId), [caseId]);
  const [actionError, setActionError] = useState<string | null>(null);
  const refresh = () => { lifecycle.refresh(); evidence.refresh(); stageEvents.refresh(); reviews.refresh(); };
  const action = async (operation: () => Promise<unknown>) => { setActionError(null); try { await operation(); refresh(); } catch (error) { setActionError(errorMessage(error)); } };
  const update = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { void action(() => updateFracasLifecycle(caseId, { containment_required: data.get("containment_required") === "on", containment_complete: data.get("containment_complete") === "on", problem_statement: data.get("problem_statement"), root_cause_method: data.get("root_cause_method"), root_cause_json: parseJson(data.get("root_cause_json"), {}), risk_assessment_json: parseJson(data.get("risk_assessment_json"), {}), effectiveness_due_date: data.get("effectiveness_due_date") || null })); } catch (error) { setActionError(`Invalid JSON: ${errorMessage(error)}`); } };
  const addEvidence = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); try { void action(() => addFracasEvidence(caseId, { evidence_type: data.get("evidence_type"), reference_type: data.get("reference_type") || null, reference_id: data.get("reference_id") || null, reference_url: data.get("reference_url") || null, title: data.get("title"), description: data.get("description"), metadata_json: parseJson(data.get("metadata_json"), {}) })); } catch (error) { setActionError(`Invalid metadata JSON: ${errorMessage(error)}`); } };
  const addReview = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); void action(() => addEffectivenessReview(caseId, { review_date: data.get("review_date"), metric_code: data.get("metric_code") || null, baseline_value: data.get("baseline_value") || null, current_value: data.get("current_value") || null, acceptance_criteria: data.get("acceptance_criteria"), outcome: data.get("outcome"), evidence_json: [], notes: data.get("notes") || null }, data.get("approve") === "on")); };
  return <><section className="reliability-v2__section"><PageHeading eyebrow="Closed-loop FRACAS" title="Investigation lifecycle" detail="Containment, root-cause evidence, actions and approved effectiveness must be complete before closure. A closed case can be reopened when recurrence is detected." /><RequestState loading={lifecycle.loading || evidence.loading || stageEvents.loading || reviews.loading} error={lifecycle.error || evidence.error || stageEvents.error || reviews.error || actionError} />{lifecycle.data && <><div className="reliability-v2__stage-line">{["DETECTED", ...FRACAS_STAGES].map((stage) => <span className={stage === lifecycle.data?.stage ? "is-current" : ""} key={stage}>{stage.replaceAll("_", " ")}</span>)}</div><form className="reliability-v2__form" onSubmit={update}><div className="reliability-v2__form-grid"><label className="reliability-v2__check-label"><input type="checkbox" name="containment_required" defaultChecked={lifecycle.data.containment_required} />Containment required</label><label className="reliability-v2__check-label"><input type="checkbox" name="containment_complete" defaultChecked={lifecycle.data.containment_complete} />Containment complete</label><label>Root-cause method<input name="root_cause_method" defaultValue={lifecycle.data.root_cause_method || ""} placeholder="5-WHY / FISHBONE / FTA" /></label><label>Effectiveness due<input type="date" name="effectiveness_due_date" defaultValue={lifecycle.data.effectiveness_due_date || ""} /></label></div><label>Problem statement<textarea name="problem_statement" rows={4} defaultValue={lifecycle.data.problem_statement || ""} /></label><div className="reliability-v2__split"><label>Root-cause JSON<textarea name="root_cause_json" rows={8} defaultValue={jsonText(lifecycle.data.root_cause_json)} /></label><label>Risk assessment JSON<textarea name="risk_assessment_json" rows={8} defaultValue={jsonText(lifecycle.data.risk_assessment_json)} /></label></div><div className="reliability-v2__actions"><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.fracas.investigate")}>Save investigation</button>{FRACAS_STAGES.map((stage) => <button className="btn btn-small btn-secondary" type="button" key={stage} onClick={() => { const rationale = window.prompt(`${stage} technical rationale`); if (rationale) void action(() => transitionFracasLifecycle(caseId, { to_stage: stage, decision: stage, rationale, payload_json: {} })); }}>{stage.replaceAll("_", " ")}</button>)}</div></form></>}</section><div className="reliability-v2__split reliability-v2__split--forms"><section className="reliability-v2__section"><PageHeading eyebrow="Frozen evidence" title="Investigation evidence" detail="Evidence hashes remain immutable after capture." /><form className="reliability-v2__form" onSubmit={addEvidence}><label>Evidence type<select name="evidence_type"><option>TECH_LOG</option><option>TASK_CARD</option><option>SHOP_REPORT</option><option>PHOTO</option><option>DOCUMENT</option><option>CALCULATION</option><option>INTERVIEW</option><option>QMS</option><option>SMS</option><option>OTHER</option></select></label><div className="reliability-v2__form-grid"><label>Reference type<input name="reference_type" /></label><label>Reference ID<input name="reference_id" /></label></div><label>Reference URL<input name="reference_url" /></label><label>Title<input name="title" required /></label><label>Description<textarea name="description" rows={3} /></label><label>Metadata JSON<textarea name="metadata_json" rows={3} defaultValue="{}" /></label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.fracas.investigate")}>Capture evidence</button></form>{(evidence.data || []).map((item) => <div className="reliability-v2__evidence-row" key={item.id}><span className={statusClass(item.evidence_type)}>{item.evidence_type}</span><strong>{item.title}</strong><small>{displayDate(item.captured_at)} · <code>{item.source_hash.slice(0, 12)}</code></small><p>{item.description}</p></div>)}</section><section className="reliability-v2__section"><PageHeading eyebrow="Measured outcome" title="Effectiveness reviews" detail="Only an approved EFFECTIVE result can satisfy the closure gate." /><form className="reliability-v2__form" onSubmit={addReview}><div className="reliability-v2__form-grid"><label>Review date<input type="date" name="review_date" defaultValue={today()} required /></label><label>Metric code<input name="metric_code" /></label><label>Baseline<input type="number" step="any" name="baseline_value" /></label><label>Current<input type="number" step="any" name="current_value" /></label><label>Outcome<select name="outcome"><option>EFFECTIVE</option><option>PARTIAL</option><option>INEFFECTIVE</option><option>INSUFFICIENT_DATA</option></select></label></div><label>Acceptance criteria<textarea name="acceptance_criteria" required rows={3} /></label><label>Notes<textarea name="notes" rows={3} /></label><label className="reliability-v2__check-label"><input type="checkbox" name="approve" />Approve this review</label><button className="btn btn-primary" disabled={!hasCapability(capabilities, "reliability.fracas.verify")}>Record review</button></form>{(reviews.data || []).map((review) => <div className="reliability-v2__evidence-row" key={review.id}><span className={statusClass(review.outcome)}>{review.outcome}</span><strong>{review.acceptance_criteria}</strong><small>{review.review_date} · {review.approved_at ? `Approved ${displayDate(review.approved_at)}` : "Not approved"}</small><p>{review.notes}</p></div>)}</section></div><section className="reliability-v2__section"><PageHeading eyebrow="Tamper-evident stage ledger" title="FRACAS decision history" detail="Each transition records the previous event hash, actor, rationale and payload." /><div className="reliability-v2__timeline">{(stageEvents.data || []).map((event) => <article key={event.id}><time>{displayDate(event.created_at)}</time><strong>{event.from_stage || "START"} → {event.to_stage}</strong><p>{event.decision}: {event.rationale}</p><code>{event.previous_hash?.slice(0, 10) || "GENESIS"} → {event.event_hash.slice(0, 10)}</code></article>)}</div></section></>;
}

export default ReliabilityAdvancedView;
