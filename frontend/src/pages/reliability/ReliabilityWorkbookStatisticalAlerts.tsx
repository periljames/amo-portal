import React, { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { apiRequest } from "../../services/apiClient";
import type { AircraftRead } from "../../services/fleet";
import type { DatasetDefinition, StatisticalAlert, WorkbookDatasetCode } from "./reliabilityWorkbookParityTypes";

type Props = {
  catalog: DatasetDefinition[];
  aircraft: AircraftRead[];
  alerts: StatisticalAlert[];
  loading: boolean;
  reload: () => Promise<void>;
};

type SourceKind = "EVENT_COUNT" | "EVENT_RATE_PER_100_FH" | "DATASET_COUNT" | "DATASET_FIELD";

function defaultStart(): string {
  const date = new Date();
  date.setMonth(date.getMonth() - 12);
  return date.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function format(value: number | null | undefined, decimals = 3): string {
  return value == null || !Number.isFinite(value) ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

export function ReliabilityWorkbookStatisticalAlerts({ catalog, aircraft, alerts, loading, reload }: Props): React.ReactElement {
  const [metricCode, setMetricCode] = useState("PIREP_RATE_PER_100_FH");
  const [metricLabel, setMetricLabel] = useState("Pilot reports per 100 flight hours");
  const [sourceKind, setSourceKind] = useState<SourceKind>("EVENT_RATE_PER_100_FH");
  const [datasetCode, setDatasetCode] = useState<WorkbookDatasetCode>("PM");
  const [metricField, setMetricField] = useState("");
  const [eventTypes, setEventTypes] = useState("PILOT_REPORT");
  const [periodStart, setPeriodStart] = useState(defaultStart());
  const [periodEnd, setPeriodEnd] = useState(today());
  const [bucket, setBucket] = useState<"WEEK" | "MONTH">("MONTH");
  const [aircraftSerial, setAircraftSerial] = useState("");
  const [ataChapter, setAtaChapter] = useState("");
  const [warningMultiplier, setWarningMultiplier] = useState("1");
  const [alertMultiplier, setAlertMultiplier] = useState("2");
  const [submitting, setSubmitting] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(alerts[0]?.id || null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const dataset = useMemo(() => catalog.find((item) => item.code === datasetCode), [catalog, datasetCode]);
  const numericFields = dataset?.fields.filter((field) => field.data_type === "decimal" || field.data_type === "integer") || [];
  const selected = alerts.find((alert) => alert.id === selectedId) || alerts[0] || null;
  const graphRows = selected?.series.map((point) => ({
    ...point,
    label: point.period,
    mean: selected.mean,
    warning: selected.warning_level,
    alert: selected.alert_level,
  })) || [];

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await apiRequest<StatisticalAlert>("/reliability/workbook-parity/statistical-alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          metric_code: metricCode.trim(),
          metric_label: metricLabel.trim(),
          source_kind: sourceKind,
          period_start: periodStart,
          period_end: periodEnd,
          bucket,
          event_types: sourceKind.startsWith("EVENT") ? eventTypes.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean) : [],
          dataset_code: sourceKind.startsWith("DATASET") ? datasetCode : null,
          metric_field: sourceKind === "DATASET_FIELD" ? metricField : null,
          aircraft_serial_number: aircraftSerial || null,
          ata_chapter: ataChapter.trim() || null,
          warning_multiplier: warningMultiplier,
          alert_multiplier: alertMultiplier,
        }),
        cacheTtlMs: 0,
      });
      setSelectedId(response.id);
      setSuccess(`${response.metric_label} alert levels calculated from ${response.sample_size} analytical periods.`);
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The statistical alert calculation failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return <>
    <section className="rel-wb__intro">
      <div><p className="reliability-v2__eyebrow">Workbook-equivalent control</p><h2>Statistical alert calculations</h2><p>Calculate the rolling mean, sample standard deviation, warning level and alert level from approved Reliability evidence. Periods without matching exposure remain uncalculated rather than becoming false zeroes.</p></div>
      <div className="rel-wb__formula"><strong>Warning</strong><span>Mean + k₁ × sample σ</span><strong>Alert</strong><span>Mean + k₂ × sample σ</span></div>
    </section>

    {error && <div className="reliability-v2__error" role="alert">{error}</div>}
    {success && <div className="rel-wb__success" role="status">{success}</div>}

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Controlled calculation</p><h3>Create statistical alert levels</h3></div><span>Minimum two populated periods</span></div>
      <form className="rel-wb__form" onSubmit={submit}>
        <div className="rel-wb__form-grid">
          <label><span>Metric code *</span><input required value={metricCode} onChange={(event) => setMetricCode(event.target.value.toUpperCase().replaceAll(" ", "_"))} /></label>
          <label><span>Metric label *</span><input required value={metricLabel} onChange={(event) => setMetricLabel(event.target.value)} /></label>
          <label><span>Source method *</span><select value={sourceKind} onChange={(event) => setSourceKind(event.target.value as SourceKind)}><option value="EVENT_COUNT">Canonical event count</option><option value="EVENT_RATE_PER_100_FH">Canonical event rate /100 FH</option><option value="DATASET_COUNT">Workbook-register count</option><option value="DATASET_FIELD">Workbook numeric field total</option></select></label>
          {sourceKind.startsWith("EVENT") ? <label><span>Event types</span><input value={eventTypes} onChange={(event) => setEventTypes(event.target.value)} placeholder="PILOT_REPORT, REPEAT_DEFECT" /></label> : <label><span>Workbook dataset</span><select value={datasetCode} onChange={(event) => { setDatasetCode(event.target.value as WorkbookDatasetCode); setMetricField(""); }}>{catalog.map((item) => <option value={item.code} key={item.code}>{item.code} · {item.name}</option>)}</select></label>}
          {sourceKind === "DATASET_FIELD" && <label><span>Numeric field *</span><select required value={metricField} onChange={(event) => setMetricField(event.target.value)}><option value="">Select numeric field</option>{numericFields.map((field) => <option value={field.key} key={field.key}>{field.label}{field.unit ? ` (${field.unit})` : ""}</option>)}</select></label>}
          <label><span>Period start *</span><input required type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
          <label><span>Period end *</span><input required type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
          <label><span>Analytical bucket</span><select value={bucket} onChange={(event) => setBucket(event.target.value as "WEEK" | "MONTH")}><option value="MONTH">Monthly</option><option value="WEEK">Weekly</option></select></label>
          <label><span>Aircraft scope</span><select value={aircraftSerial} onChange={(event) => setAircraftSerial(event.target.value)}><option value="">Fleet</option>{aircraft.map((item) => <option value={item.serial_number} key={item.serial_number}>{item.registration || item.serial_number}</option>)}</select></label>
          <label><span>ATA scope</span><input value={ataChapter} onChange={(event) => setAtaChapter(event.target.value)} placeholder="Fleet-wide if blank" /></label>
          <label><span>Warning multiplier k₁</span><input type="number" step="0.1" min="0" required value={warningMultiplier} onChange={(event) => setWarningMultiplier(event.target.value)} /></label>
          <label><span>Alert multiplier k₂</span><input type="number" step="0.1" min="0.1" required value={alertMultiplier} onChange={(event) => setAlertMultiplier(event.target.value)} /></label>
        </div>
        <div className="rel-wb__form-actions"><button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? "Calculating and retaining evidence…" : "Calculate statistical levels"}</button></div>
      </form>
    </section>

    {selected && <section className="rel-wb__panel rel-wb__panel--chart">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Retained result #{selected.id}</p><h3>{selected.metric_label}</h3><p>{selected.formula}</p></div><select aria-label="Select retained calculation" value={selected.id} onChange={(event) => setSelectedId(Number(event.target.value))}>{alerts.map((alert) => <option value={alert.id} key={alert.id}>{alert.metric_code} · {alert.period_end}</option>)}</select></div>
      <div className="rel-wb__metrics">
        <Metric label="Sample periods" value={String(selected.sample_size)} />
        <Metric label="Mean" value={format(selected.mean)} />
        <Metric label="Sample σ" value={format(selected.sample_stddev)} />
        <Metric label="Warning" value={format(selected.warning_level)} />
        <Metric label="Alert" value={format(selected.alert_level)} />
      </div>
      <div className="rel-wb__chart" role="img" aria-label={`${selected.metric_label} statistical control chart`}>
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={graphRows} margin={{ top: 20, right: 30, bottom: 30, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" angle={graphRows.length > 12 ? -35 : 0} textAnchor={graphRows.length > 12 ? "end" : "middle"} height={graphRows.length > 12 ? 80 : 40} />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="value" name="Measured value" strokeWidth={2.5} connectNulls={false} />
            <ReferenceLine y={selected.mean} label="Mean" strokeDasharray="3 3" />
            <ReferenceLine y={selected.warning_level} label="Warning" strokeDasharray="6 4" />
            <ReferenceLine y={selected.alert_level} label="Alert" strokeDasharray="6 4" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="rel-wb__table-wrap"><table className="rel-wb__table"><thead><tr><th>Period</th><th>Numerator</th><th>Exposure</th><th>Measured value</th><th>Classification</th></tr></thead><tbody>{selected.series.map((point) => {
        const value = point.value;
        const classification = value == null ? "NO EXPOSURE" : value >= selected.alert_level ? "ALERT" : value >= selected.warning_level ? "WARNING" : "NORMAL";
        return <tr key={point.period}><td>{point.period}</td><td>{format(point.numerator, 0)}</td><td>{format(point.denominator)}</td><td>{format(value)}</td><td><span className={`rel-wb__classification rel-wb__classification--${classification.toLowerCase().replaceAll(" ", "-")}`}>{classification}</span></td></tr>;
      })}</tbody></table></div>
    </section>}

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Calculation evidence register</p><h3>Statistical alert history</h3></div><span>{alerts.length} loaded</span></div>
      {loading ? <div className="reliability-v2__loading">Loading calculations…</div> : <div className="rel-wb__table-wrap"><table className="rel-wb__table"><thead><tr><th>Metric</th><th>Scope</th><th>Period</th><th>Mean / σ</th><th>Warning / alert</th><th>Generated</th></tr></thead><tbody>{alerts.map((alert) => <tr key={alert.id} onClick={() => setSelectedId(alert.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") setSelectedId(alert.id); }}><td><strong>{alert.metric_label}</strong><span>{alert.metric_code}</span></td><td>{alert.scope_value || alert.scope_type}</td><td>{alert.period_start} → {alert.period_end}<small>{alert.bucket.toLowerCase()} · n={alert.sample_size}</small></td><td>{format(alert.mean)} / {format(alert.sample_stddev)}</td><td>{format(alert.warning_level)} / {format(alert.alert_level)}</td><td>{new Date(alert.generated_at).toLocaleString()}</td></tr>)}{alerts.length === 0 && <tr><td colSpan={6}>No statistical alert calculations have been retained.</td></tr>}</tbody></table></div>}
    </section>
  </>;
}

function Metric({ label, value }: { label: string; value: string }): React.ReactElement {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
