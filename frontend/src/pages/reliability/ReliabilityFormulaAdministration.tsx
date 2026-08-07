import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  createReliabilityMetricDefinition,
  createReliabilityThresholdVersion,
  executeReliabilityCalculation,
  getReliabilityCapabilities,
  listReliabilityCalculationRuns,
  listReliabilityMetricDefinitions,
  listReliabilityProgrammeVersions,
  listReliabilityThresholdVersions,
  type ReliabilityCalculationRun,
  type ReliabilityCapabilitySnapshot,
  type ReliabilityMetricDefinition,
  type ReliabilityProgrammeVersion,
  type ReliabilityThresholdVersion,
} from "../../services/reliability";
import type { CalculationFormula } from "./reliabilityAnalyticsTypes";

const EVENT_TYPES = [
  "DEFECT",
  "REPEAT_DEFECT",
  "PILOT_REPORT",
  "CABIN_REPORT",
  "TECHNICAL_DELAY",
  "TECHNICAL_CANCELLATION",
  "RETURN_TO_GATE",
  "AIR_TURNBACK",
  "DIVERSION",
  "IN_FLIGHT_SHUTDOWN",
  "ABORTED_TAKEOFF",
  "MEL_DEFERRAL",
  "CDL_DEFERRAL",
  "UNSCHEDULED_REMOVAL",
  "SCHEDULED_REMOVAL",
  "REMOVAL",
  "INSTALLATION",
  "SHOP_FINDING",
  "NO_FAULT_FOUND",
  "OCTM",
  "ECTM",
  "EHM_ALERT",
  "FRACAS",
  "MAINTENANCE_ERROR",
  "SUPPLIER_ESCAPE",
  "SAFETY_EVENT",
  "OTHER",
];

const EMPTY_CAPABILITIES: ReliabilityCapabilitySnapshot = { capabilities: [], superuser: false };

function hasCapability(snapshot: ReliabilityCapabilitySnapshot, capability: string): boolean {
  return snapshot.superuser || snapshot.capabilities.includes(capability);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The Reliability operation failed.";
}

function optionalNumber(data: FormData, name: string): number | null {
  const raw = String(data.get(name) || "").trim();
  return raw === "" ? null : Number(raw);
}

function optionalText(data: FormData, name: string): string | null {
  const raw = String(data.get(name) || "").trim();
  return raw || null;
}

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusClass(value?: string | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "unknown").toLowerCase().replaceAll("_", "-")}`;
}

export function ReliabilityFormulaAdministration({ formulae }: { formulae: CalculationFormula[] }): React.ReactElement {
  const [versions, setVersions] = useState<ReliabilityProgrammeVersion[]>([]);
  const [metrics, setMetrics] = useState<ReliabilityMetricDefinition[]>([]);
  const [thresholds, setThresholds] = useState<ReliabilityThresholdVersion[]>([]);
  const [runs, setRuns] = useState<ReliabilityCalculationRun[]>([]);
  const [capabilities, setCapabilities] = useState<ReliabilityCapabilitySnapshot>(EMPTY_CAPABILITIES);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [selectedMetric, setSelectedMetric] = useState("");
  const [calculationMetric, setCalculationMetric] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [versionRows, metricRows, thresholdRows, calculationRows, capabilityRows] = await Promise.all([
        listReliabilityProgrammeVersions(),
        listReliabilityMetricDefinitions(),
        listReliabilityThresholdVersions(),
        listReliabilityCalculationRuns(),
        getReliabilityCapabilities(),
      ]);
      setVersions(versionRows);
      setMetrics(metricRows);
      setThresholds(thresholdRows);
      setRuns(calculationRows);
      setCapabilities(capabilityRows);
      setSelectedVersion((current) => current || versionRows.find((row) => row.status === "EFFECTIVE")?.id || versionRows[0]?.id || "");
      setSelectedMetric((current) => current || metricRows[0]?.id || "");
      setCalculationMetric((current) => current || metricRows[0]?.id || "");
    } catch (caught: unknown) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const formulaByMetric = useMemo(() => new Map(
    formulae.filter((formula) => formula.origin === "PROGRAMME").map((formula) => [formula.code.replace(/^programme\./, ""), formula]),
  ), [formulae]);

  const submitMetric = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedVersion) {
      setError("Select a controlled programme version before creating a metric.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      const created = await createReliabilityMetricDefinition(selectedVersion, {
        code: String(data.get("code") || "").trim(),
        name: String(data.get("name") || "").trim(),
        description: optionalText(data, "description"),
        scope_type: String(data.get("scope_type") || "FLEET"),
        method: String(data.get("method") || "RATE"),
        numerator_event_types: Array.from(data.getAll("numerator_event_types"), String),
        denominator_type: String(data.get("denominator_type") || "FH"),
        multiplier: Number(data.get("multiplier") || 100),
        window_days: Number(data.get("window_days") || 30),
        schedule_interval_minutes: Number(data.get("schedule_interval_minutes") || 1440),
        minimum_exposure: Number(data.get("minimum_exposure") || 1),
        direction: String(data.get("direction") || "ABOVE"),
        formula_version: String(data.get("formula_version") || "1").trim(),
      });
      setMetrics((current) => [...current, created].sort((left, right) => left.code.localeCompare(right.code)));
      setSelectedMetric(created.id);
      setCalculationMetric(created.id);
      form.reset();
      setMessage(`Metric ${created.code} was created in the controlled programme version.`);
    } catch (caught: unknown) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  const submitThreshold = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedMetric) {
      setError("Select a metric before creating a threshold version.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      const created = await createReliabilityThresholdVersion(selectedMetric, {
        version: String(data.get("version") || "").trim(),
        caution_value: optionalNumber(data, "caution_value"),
        alert_value: optionalNumber(data, "alert_value"),
        lower_caution_value: optionalNumber(data, "lower_caution_value"),
        lower_alert_value: optionalNumber(data, "lower_alert_value"),
        minimum_exposure: optionalNumber(data, "minimum_exposure"),
        rationale: String(data.get("rationale") || "").trim(),
        effective_from: optionalText(data, "effective_from"),
      });
      setThresholds((current) => [created, ...current]);
      form.reset();
      setMessage(`Threshold version ${created.version} was created as ${created.status}.`);
    } catch (caught: unknown) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  const submitCalculation = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!calculationMetric) {
      setError("Select a metric before executing a calculation.");
      return;
    }
    const data = new FormData(event.currentTarget);
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      const created = await executeReliabilityCalculation({
        metric_definition_id: calculationMetric,
        period_start: optionalText(data, "period_start"),
        period_end: optionalText(data, "period_end"),
        scope_type: optionalText(data, "scope_type"),
        scope_id: optionalText(data, "scope_id"),
      });
      setRuns((current) => [created, ...current.filter((row) => row.id !== created.id)]);
      setMessage(`Calculation completed with status ${created.status}.`);
    } catch (caught: unknown) {
      setError(errorMessage(caught));
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="reliability-formula-admin" id="reliability-formula-administration" aria-labelledby="reliability-formula-admin-heading">
      <div className="reliability-formula-admin__heading">
        <div>
          <p className="reliability-v2__eyebrow">Programme configuration</p>
          <h2 id="reliability-formula-admin-heading">Metric, threshold and calculation control</h2>
          <p>All calculation inputs are explicit. Formula version, method, exposure, direction, thresholds and retained execution evidence are available in the frontend.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void load()} disabled={loading || working}>Refresh records</button>
      </div>

      {loading && <div className="reliability-v2__loading" role="status">Loading governed metric records…</div>}
      {error && <div className="reliability-v2__error" role="alert">{error}</div>}
      {message && <div className="reliability-formula-admin__message" role="status">{message}</div>}

      {!loading && (
        <div className="reliability-formula-admin__forms">
          <form className="reliability-formula-admin__form" onSubmit={(event) => void submitMetric(event)}>
            <h3>Define metric</h3>
            <label>Programme version<select value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)} required><option value="">Select version</option>{versions.map((version) => <option value={version.id} key={version.id}>{version.revision} · {version.status}</option>)}</select></label>
            <div className="reliability-formula-admin__form-grid">
              <label>Metric code<input name="code" required placeholder="DEFECT_RATE_100FH" /></label>
              <label>Metric name<input name="name" required /></label>
              <label>Scope<select name="scope_type"><option>FLEET</option><option>AIRCRAFT</option><option>ATA</option><option>COMPONENT</option><option>ENGINE</option></select></label>
              <label>Method<select name="method"><option>RATE</option><option>COUNT</option><option>PERCENT</option><option>MTBUR</option><option>NFF_RATE</option></select></label>
              <label>Denominator<select name="denominator_type"><option>FH</option><option>FC</option><option>FLIGHTS</option><option>DAYS</option><option>POPULATION</option><option>NONE</option></select></label>
              <label>Direction<select name="direction"><option>ABOVE</option><option>BELOW</option><option>TWO_SIDED</option></select></label>
              <label>Multiplier<input type="number" step="any" min="0" name="multiplier" defaultValue="100" required /></label>
              <label>Window days<input type="number" min="1" max="3650" name="window_days" defaultValue="30" required /></label>
              <label>Schedule interval (minutes)<input type="number" min="60" max="525600" name="schedule_interval_minutes" defaultValue="1440" required /></label>
              <label>Minimum exposure<input type="number" step="any" min="0" name="minimum_exposure" defaultValue="1" required /></label>
              <label>Formula version<input name="formula_version" defaultValue="1" required /></label>
            </div>
            <label>Description and methodology<textarea name="description" rows={3} placeholder="Define inclusion, exclusion, exposure and interpretation rules." /></label>
            <fieldset className="reliability-formula-admin__events"><legend>Numerator event types</legend>{EVENT_TYPES.map((eventType) => <label key={eventType}><input type="checkbox" name="numerator_event_types" value={eventType} />{eventType.replaceAll("_", " ")}</label>)}</fieldset>
            <button className="btn btn-primary" disabled={working || !hasCapability(capabilities, "reliability.metric.manage")}>Create metric definition</button>
            {!hasCapability(capabilities, "reliability.metric.manage") && <small>Required capability: reliability.metric.manage</small>}
          </form>

          <form className="reliability-formula-admin__form" onSubmit={(event) => void submitThreshold(event)}>
            <h3>Define threshold version</h3>
            <label>Metric<select value={selectedMetric} onChange={(event) => setSelectedMetric(event.target.value)} required><option value="">Select metric</option>{metrics.map((metric) => <option value={metric.id} key={metric.id}>{metric.code} · {metric.name}</option>)}</select></label>
            <div className="reliability-formula-admin__form-grid">
              <label>Version<input name="version" required placeholder="A" /></label>
              <label>Upper caution<input type="number" step="any" name="caution_value" /></label>
              <label>Upper alert<input type="number" step="any" name="alert_value" /></label>
              <label>Lower caution<input type="number" step="any" name="lower_caution_value" /></label>
              <label>Lower alert<input type="number" step="any" name="lower_alert_value" /></label>
              <label>Minimum exposure<input type="number" step="any" min="0" name="minimum_exposure" /></label>
              <label>Effective from<input type="date" name="effective_from" /></label>
            </div>
            <label>Engineering rationale<textarea name="rationale" required minLength={5} rows={5} /></label>
            <button className="btn btn-primary" disabled={working || !hasCapability(capabilities, "reliability.metric.manage")}>Create threshold version</button>
          </form>

          <form className="reliability-formula-admin__form" onSubmit={(event) => void submitCalculation(event)}>
            <h3>Execute governed calculation</h3>
            <label>Metric<select value={calculationMetric} onChange={(event) => setCalculationMetric(event.target.value)} required><option value="">Select metric</option>{metrics.map((metric) => <option value={metric.id} key={metric.id}>{metric.code} · v{metric.formula_version}</option>)}</select></label>
            <div className="reliability-formula-admin__form-grid">
              <label>Period start<input type="date" name="period_start" /></label>
              <label>Period end<input type="date" name="period_end" /></label>
              <label>Scope type<select name="scope_type" defaultValue=""><option value="">Definition default</option><option>FLEET</option><option>AIRCRAFT</option><option>ATA</option><option>COMPONENT</option><option>ENGINE</option></select></label>
              <label>Scope identifier<input name="scope_id" placeholder="FLEET or aircraft serial" /></label>
            </div>
            <button className="btn btn-primary" disabled={working || !hasCapability(capabilities, "reliability.metric.execute")}>Run calculation</button>
            {!hasCapability(capabilities, "reliability.metric.execute") && <small>Required capability: reliability.metric.execute</small>}
          </form>
        </div>
      )}

      <div className="reliability-formula-admin__register">
        <h3>Metric definitions</h3>
        <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Metric</th><th>Method</th><th>Structured formula</th><th>Exposure control</th><th>Schedule</th><th>Status</th></tr></thead><tbody>
          {metrics.map((metric) => { const formula = formulaByMetric.get(metric.code); return <tr key={metric.id}><td><strong>{metric.code}</strong><small>{metric.name}</small><p>{metric.description || "No methodology description recorded."}</p></td><td>{metric.method}<small>{metric.scope_type} · {metric.direction}</small></td><td>{formula ? <a href={`#formula-${formula.code}`}>View rendered formula v{formula.version}</a> : <span>Formula becomes available after dashboard refresh.</span>}<small>{metric.numerator_event_types.join(", ") || "No event numerator"}</small></td><td>{metric.denominator_type} × {metric.multiplier}<small>Minimum {metric.minimum_exposure}</small></td><td>{metric.window_days} day window<small>Every {metric.schedule_interval_minutes} minutes</small></td><td><span className={statusClass(metric.active ? "ACTIVE" : "INACTIVE")}>{metric.active ? "ACTIVE" : "INACTIVE"}</span><small>Formula v{metric.formula_version}</small></td></tr>; })}
          {!metrics.length && <tr><td colSpan={6}>No controlled metric definitions are available.</td></tr>}
        </tbody></table></div>
      </div>

      <div className="reliability-formula-admin__register">
        <h3>Threshold versions</h3>
        <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Metric</th><th>Version</th><th>Upper limits</th><th>Lower limits</th><th>Minimum exposure</th><th>Effective period</th><th>Rationale</th><th>Status</th></tr></thead><tbody>
          {thresholds.map((threshold) => <tr key={threshold.id}><td>{metrics.find((metric) => metric.id === threshold.metric_definition_id)?.code || threshold.metric_definition_id}</td><td>{threshold.version}</td><td>Caution {threshold.caution_value ?? "—"}<small>Alert {threshold.alert_value ?? "—"}</small></td><td>Caution {threshold.lower_caution_value ?? "—"}<small>Alert {threshold.lower_alert_value ?? "—"}</small></td><td>{threshold.minimum_exposure ?? "Definition default"}</td><td>{threshold.effective_from || "Not effective"}<small>to {threshold.effective_to || "open"}</small></td><td>{threshold.rationale}</td><td><span className={statusClass(threshold.status)}>{threshold.status}</span><small>{displayDate(threshold.approved_at)}</small></td></tr>)}
          {!thresholds.length && <tr><td colSpan={8}>No controlled threshold versions are available.</td></tr>}
        </tbody></table></div>
      </div>

      <div className="reliability-formula-admin__register">
        <h3>Retained calculation evidence</h3>
        <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Created</th><th>Period</th><th>Metric and formula</th><th>Scope</th><th>Numerator</th><th>Denominator</th><th>Value</th><th>95% confidence</th><th>Status</th><th>Evidence</th></tr></thead><tbody>
          {runs.map((run) => { const metric = metrics.find((row) => row.id === run.metric_definition_id); return <tr key={run.id}><td>{displayDate(run.created_at)}</td><td>{run.period_start} – {run.period_end}</td><td><strong>{metric?.code || run.metric_definition_id}</strong><small>Formula v{run.formula_version}</small></td><td>{run.scope_type}: {run.scope_id}</td><td>{run.numerator ?? "—"}</td><td>{run.denominator ?? "—"}</td><td>{run.value ?? "—"}</td><td>{run.confidence_lower ?? "—"} – {run.confidence_upper ?? "—"}<small>n={run.sample_size}</small></td><td><span className={statusClass(run.status)}>{run.status}</span>{run.small_fleet && <small>Small-fleet caution</small>}</td><td><code>{run.result_hash.slice(0, 16)}</code><details><summary>Source lineage</summary><pre>{JSON.stringify(run.source_lineage_json, null, 2)}</pre></details></td></tr>; })}
          {!runs.length && <tr><td colSpan={10}>No governed calculation runs are available.</td></tr>}
        </tbody></table></div>
      </div>
    </section>
  );
}
