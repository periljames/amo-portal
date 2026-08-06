import React, { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  calculateStatisticalAlert,
  createMapping,
  listMappings,
  listStatisticalAlerts,
  readMappingParity,
  readParityContracts,
  seedDefaultMappings,
} from "./reliabilityWorkbookParityApi";
import { formatValue, statisticalFormulaMathMl } from "./reliabilityWorkbookParityModel";
import {
  DATASET_ORDER,
  WORKBOOK_PROFILES,
  type MappingCreate,
  type MappingRow,
  type ParityContracts,
  type ParityRow,
  type StatisticalAlert,
  type StatisticalAlertRequest,
  type WorkbookDatasetCode,
  type WorkbookFieldDefinition,
} from "./reliabilityWorkbookParityTypes";

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
  "UNSCHEDULED_REMOVAL",
  "SAFETY_EVENT",
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthsAgo(months: number): string {
  const value = new Date();
  value.setMonth(value.getMonth() - months);
  return value.toISOString().slice(0, 10);
}

export function ReliabilityStatisticalAlerts({ catalog }: { catalog: WorkbookFieldDefinition[] }): React.ReactElement {
  const [request, setRequest] = useState<StatisticalAlertRequest>({
    metric_code: "TECH_EVENTS_MONTHLY",
    metric_label: "Monthly technical events",
    source_kind: "EVENT_COUNT",
    period_start: monthsAgo(12),
    period_end: today(),
    bucket: "MONTH",
    event_types: ["DEFECT", "PILOT_REPORT", "TECHNICAL_DELAY", "TECHNICAL_CANCELLATION"],
    dataset_code: null,
    metric_field: null,
    aircraft_serial_number: null,
    ata_chapter: null,
    warning_multiplier: 1,
    alert_multiplier: 2,
  });
  const [alerts, setAlerts] = useState<StatisticalAlert[]>([]);
  const [selected, setSelected] = useState<StatisticalAlert | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await listStatisticalAlerts(100);
      setAlerts(rows);
      setSelected((current) => current || rows[0] || null);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Statistical alert history could not be loaded.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const dataset = catalog.find((item) => item.code === request.dataset_code);
  const numericFields = dataset?.fields.filter((field) => field.data_type === "decimal" || field.data_type === "integer") || [];
  const datasetSource = request.source_kind === "DATASET_COUNT" || request.source_kind === "DATASET_FIELD";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (datasetSource && !request.dataset_code) {
      setError("Select a workbook dataset for this calculation.");
      return;
    }
    if (request.source_kind === "DATASET_FIELD" && !request.metric_field) {
      setError("Select a numeric dataset field.");
      return;
    }
    if (request.source_kind.startsWith("EVENT") && request.event_types.length === 0) {
      setError("Select at least one canonical event type.");
      return;
    }
    setLoading(true);
    try {
      const result = await calculateStatisticalAlert(request);
      setSelected(result);
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The statistical alert calculation failed.");
    } finally {
      setLoading(false);
    }
  };

  return <div className="rel-wp__governance-grid">
    <section className="rel-wp__panel">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Workbook-equivalent control limits</p><h2>Statistical alert calculation</h2></div><span>Sample standard deviation</span></div>
      {error && <div className="rel-wp__error" role="alert">{error}</div>}
      <form className="rel-wp__form" onSubmit={submit}>
        <div className="rel-wp__form-grid">
          <label>Metric code<input required value={request.metric_code} onChange={(event) => setRequest({ ...request, metric_code: event.target.value.toUpperCase().replaceAll(" ", "_") })} /></label>
          <label>Metric label<input required value={request.metric_label} onChange={(event) => setRequest({ ...request, metric_label: event.target.value })} /></label>
          <label>Source<select value={request.source_kind} onChange={(event) => setRequest({ ...request, source_kind: event.target.value as StatisticalAlertRequest["source_kind"], dataset_code: null, metric_field: null })}><option value="EVENT_COUNT">Canonical event count</option><option value="EVENT_RATE_PER_100_FH">Event rate per 100 FH</option><option value="DATASET_COUNT">Workbook dataset count</option><option value="DATASET_FIELD">Workbook numeric field</option></select></label>
          <label>Bucket<select value={request.bucket} onChange={(event) => setRequest({ ...request, bucket: event.target.value as "WEEK" | "MONTH" })}><option value="MONTH">Month</option><option value="WEEK">Week</option></select></label>
          <label>Period start<input type="date" required value={request.period_start} onChange={(event) => setRequest({ ...request, period_start: event.target.value })} /></label>
          <label>Period end<input type="date" required value={request.period_end} onChange={(event) => setRequest({ ...request, period_end: event.target.value })} /></label>
          <label>Warning multiplier<input type="number" min="0" step="0.1" value={request.warning_multiplier} onChange={(event) => setRequest({ ...request, warning_multiplier: Number(event.target.value) })} /></label>
          <label>Alert multiplier<input type="number" min="0.1" step="0.1" value={request.alert_multiplier} onChange={(event) => setRequest({ ...request, alert_multiplier: Number(event.target.value) })} /></label>
          <label>Aircraft scope<input value={request.aircraft_serial_number || ""} onChange={(event) => setRequest({ ...request, aircraft_serial_number: event.target.value || null })} placeholder="Blank for fleet" /></label>
          <label>ATA scope<input value={request.ata_chapter || ""} onChange={(event) => setRequest({ ...request, ata_chapter: event.target.value || null })} placeholder="Blank for all ATA" /></label>
          {datasetSource && <label>Dataset<select required value={request.dataset_code || ""} onChange={(event) => setRequest({ ...request, dataset_code: event.target.value as WorkbookDatasetCode, metric_field: null })}><option value="">Select…</option>{DATASET_ORDER.map((code) => <option key={code} value={code}>{code} — {catalog.find((item) => item.code === code)?.name}</option>)}</select></label>}
          {request.source_kind === "DATASET_FIELD" && <label>Numeric field<select required value={request.metric_field || ""} onChange={(event) => setRequest({ ...request, metric_field: event.target.value || null })}><option value="">Select…</option>{numericFields.map((field) => <option key={field.key} value={field.key}>{field.label}</option>)}</select></label>}
        </div>
        {request.source_kind.startsWith("EVENT") && <fieldset><legend>Canonical event population</legend><div className="rel-wp__event-options">{EVENT_TYPES.map((eventType) => <label key={eventType}><input type="checkbox" checked={request.event_types.includes(eventType)} onChange={(event) => setRequest({ ...request, event_types: event.target.checked ? [...request.event_types, eventType] : request.event_types.filter((item) => item !== eventType) })} />{eventType.replaceAll("_", " ")}</label>)}</div></fieldset>}
        <div className="rel-wp__form-actions"><button type="submit" className="btn btn-primary" disabled={loading}>{loading ? "Calculating…" : "Calculate and retain snapshot"}</button></div>
      </form>
    </section>

    <section className="rel-wp__panel rel-wp__chart-panel">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Controlled result</p><h2>{selected?.metric_label || "No calculation selected"}</h2></div>{selected && <span>n = {selected.sample_size}</span>}</div>
      {selected ? <>
        <div className="rel-wp__metric-strip rel-wp__metric-strip--compact"><div><span>Mean</span><strong>{selected.mean.toFixed(4)}</strong></div><div><span>Sample σ</span><strong>{selected.sample_stddev.toFixed(4)}</strong></div><div><span>Warning</span><strong>{selected.warning_level.toFixed(4)}</strong></div><div><span>Alert</span><strong>{selected.alert_level.toFixed(4)}</strong></div></div>
        <div className="rel-wp__formula" dangerouslySetInnerHTML={{ __html: statisticalFormulaMathMl(selected) }} />
        <code className="rel-wp__formula-source">{selected.formula}</code>
        <div className="rel-wp__chart" data-testid="statistical-alert-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={selected.series}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="period" /><YAxis domain={["auto", "auto"]} /><Tooltip /><Legend /><ReferenceLine y={selected.mean} strokeDasharray="4 4" label="Mean" /><ReferenceLine y={selected.warning_level} strokeDasharray="6 3" label="Warning" /><ReferenceLine y={selected.alert_level} strokeDasharray="2 2" label="Alert" /><Line type="monotone" dataKey="value" name="Observed value" connectNulls={false} /></LineChart></ResponsiveContainer></div>
        <div className="rel-wp__table-wrap"><table className="rel-wp__table"><thead><tr><th>Period</th><th>Value</th><th>Numerator</th><th>Denominator</th><th>Disposition</th></tr></thead><tbody>{selected.series.map((point) => <tr key={point.period}><td>{point.period}</td><td>{formatValue(point.value)}</td><td>{formatValue(point.numerator)}</td><td>{formatValue(point.denominator)}</td><td>{point.value == null ? "WITHHELD" : point.value >= selected.alert_level ? "ALERT" : point.value >= selected.warning_level ? "WATCH" : "NORMAL"}</td></tr>)}</tbody></table></div>
      </> : <p className="rel-wp__empty">Run or select a retained calculation to inspect its series and limits.</p>}
    </section>

    <section className="rel-wp__panel rel-wp__span-all">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Immutable history</p><h2>Retained statistical snapshots</h2></div><button type="button" className="btn btn-secondary" onClick={() => void load()}>Refresh</button></div>
      <div className="rel-wp__table-wrap"><table className="rel-wp__table"><thead><tr><th>Generated</th><th>Metric</th><th>Source</th><th>Period</th><th>n</th><th>Mean</th><th>σ</th><th>Alert</th></tr></thead><tbody>{alerts.map((alert) => <tr key={alert.id} className={selected?.id === alert.id ? "is-selected" : ""}><td><button type="button" className="rel-wp__link-button" onClick={() => setSelected(alert)}>{new Date(alert.generated_at).toLocaleString()}</button></td><td>{alert.metric_label}</td><td>{alert.source_kind.replaceAll("_", " ")}</td><td>{alert.period_start} – {alert.period_end}</td><td>{alert.sample_size}</td><td>{alert.mean.toFixed(4)}</td><td>{alert.sample_stddev.toFixed(4)}</td><td>{alert.alert_level.toFixed(4)}</td></tr>)}{alerts.length === 0 && <tr><td colSpan={8}>No statistical calculations have been retained.</td></tr>}</tbody></table></div>
    </section>
  </div>;
}

export function ReliabilityMappingParity({ catalog }: { catalog: WorkbookFieldDefinition[] }): React.ReactElement {
  const [profile, setProfile] = useState<string>(WORKBOOK_PROFILES[0]);
  const [mappings, setMappings] = useState<MappingRow[]>([]);
  const [parity, setParity] = useState<ParityRow[]>([]);
  const [contracts, setContracts] = useState<ParityContracts | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [aliases, setAliases] = useState("");
  const [transform, setTransform] = useState("{}");
  const [draft, setDraft] = useState<MappingCreate>({
    profile_code: WORKBOOK_PROFILES[0], profile_name: "Safarilink C208B Reliability Programme", workbook_family: "C208B",
    dataset_code: "AU", source_sheet: "AU", source_column: "", canonical_field: "event_date", data_type: "text",
    required: false, unit: null, aliases: [], transform: {},
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [mappingRows, parityRows, contractRows] = await Promise.all([listMappings(profile), readMappingParity(), readParityContracts()]);
      setMappings(mappingRows);
      setParity(parityRows);
      setContracts(contractRows);
      setError(null);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Workbook parity evidence could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [profile]);

  useEffect(() => { void load(); }, [load]);

  const definition = catalog.find((item) => item.code === draft.dataset_code);
  const canonicalFields = ["event_date", "event_end_date", "aircraft_serial_number", "ata_chapter", "reference_code", "title", "description", ...(definition?.fields.map((field) => field.key) || [])];
  const profileContract = contracts?.mapping.profiles[profile];

  const seed = async () => {
    setLoading(true);
    try {
      const result = await seedDefaultMappings();
      setNotice(`${result.total_active} active mapping rows cover ${result.profiles.length} workbook profiles.`);
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Default mappings could not be seeded.");
    } finally {
      setLoading(false);
    }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      const parsed = JSON.parse(transform || "{}") as Record<string, unknown>;
      await createMapping({ ...draft, profile_code: profile, aliases: aliases.split(",").map((item) => item.trim()).filter(Boolean), transform: parsed });
      setNotice("The versioned field mapping was created.");
      setAliases("");
      setTransform("{}");
      setDraft((current) => ({ ...current, source_column: "" }));
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The mapping could not be created.");
    } finally {
      setLoading(false);
    }
  };

  return <div className="rel-wp__governance-grid">
    <section className="rel-wp__panel rel-wp__span-all">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Formal workbook contract</p><h2>Field mapping and parity</h2></div><div className="rel-wp__section-actions"><button type="button" className="btn btn-primary" disabled={loading} onClick={() => void seed()}>Seed or repair defaults</button><button type="button" className="btn btn-secondary" onClick={() => void load()}>Refresh</button></div></div>
      {notice && <div className="rel-wp__notice" role="status">{notice}</div>}
      {error && <div className="rel-wp__error" role="alert">{error}</div>}
      <label className="rel-wp__profile-select">Workbook profile<select value={profile} onChange={(event) => { setProfile(event.target.value); setDraft((current) => ({ ...current, profile_code: event.target.value })); }}>{WORKBOOK_PROFILES.map((item) => <option key={item}>{item}</option>)}</select></label>
      <div className="rel-wp__parity-cards">{parity.map((row) => <article key={row.dataset_code} className={row.missing_required_fields.length ? "has-gap" : "is-complete"}><span>{row.dataset_code}</span><strong>{row.coverage_pct.toFixed(1)}%</strong><small>{row.record_count} records · {row.missing_required_fields.length ? `${row.missing_required_fields.length} required gaps` : "required fields covered"}</small></article>)}</div>
    </section>

    <section className="rel-wp__panel">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Profile assurance</p><h3>{profile}</h3></div></div>
      <div className="rel-wp__table-wrap"><table className="rel-wp__table"><thead><tr><th>Dataset</th><th>Mapped</th><th>Expected</th><th>Coverage</th><th>Required gaps</th></tr></thead><tbody>{DATASET_ORDER.map((code) => { const row = profileContract?.[code]; return <tr key={code}><td>{code}</td><td>{row?.mapped_fields ?? 0}</td><td>{row?.expected_fields ?? catalog.find((item) => item.code === code)?.fields.length ?? 0}</td><td>{row?.coverage_pct?.toFixed(1) ?? "0.0"}%</td><td>{row?.missing_required_fields.join(", ") || "None"}</td></tr>; })}</tbody></table></div>
    </section>

    <section className="rel-wp__panel">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Operator extension</p><h3>Create mapping row</h3></div></div>
      <form className="rel-wp__form" onSubmit={save}><div className="rel-wp__form-grid">
        <label>Profile name<input required value={draft.profile_name} onChange={(event) => setDraft({ ...draft, profile_name: event.target.value })} /></label>
        <label>Workbook family<input required value={draft.workbook_family} onChange={(event) => setDraft({ ...draft, workbook_family: event.target.value })} /></label>
        <label>Dataset<select value={draft.dataset_code} onChange={(event) => { const code = event.target.value as WorkbookDatasetCode; const selectedDefinition = catalog.find((item) => item.code === code); setDraft({ ...draft, dataset_code: code, source_sheet: selectedDefinition?.workbook_sheet_names[0] || code, canonical_field: "event_date" }); }}>{DATASET_ORDER.map((code) => <option key={code}>{code}</option>)}</select></label>
        <label>Source sheet<input required value={draft.source_sheet} onChange={(event) => setDraft({ ...draft, source_sheet: event.target.value })} /></label>
        <label>Source column<input required value={draft.source_column} onChange={(event) => setDraft({ ...draft, source_column: event.target.value })} /></label>
        <label>Canonical field<select value={draft.canonical_field} onChange={(event) => setDraft({ ...draft, canonical_field: event.target.value })}>{canonicalFields.map((field) => <option key={field}>{field}</option>)}</select></label>
        <label>Data type<select value={draft.data_type} onChange={(event) => setDraft({ ...draft, data_type: event.target.value })}><option>text</option><option>date</option><option>datetime</option><option>decimal</option><option>integer</option><option>boolean</option></select></label>
        <label>Unit<input value={draft.unit || ""} onChange={(event) => setDraft({ ...draft, unit: event.target.value || null })} /></label>
        <label className="rel-wp__span-2">Header aliases<input value={aliases} onChange={(event) => setAliases(event.target.value)} placeholder="Comma-separated legacy headers" /></label>
        <label className="rel-wp__span-2">Transform JSON<textarea rows={3} value={transform} onChange={(event) => setTransform(event.target.value)} /></label>
        <label className="rel-wp__checkbox"><input type="checkbox" checked={draft.required} onChange={(event) => setDraft({ ...draft, required: event.target.checked })} />Required source column</label>
      </div><div className="rel-wp__form-actions"><button className="btn btn-primary" type="submit" disabled={loading}>Create mapping</button></div></form>
    </section>

    <section className="rel-wp__panel rel-wp__span-all">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Active profile rows</p><h3>Source-to-canonical mapping register</h3></div><span>{mappings.length} rows</span></div>
      <div className="rel-wp__table-wrap rel-wp__table-wrap--tall"><table className="rel-wp__table"><thead><tr><th>Dataset</th><th>Sheet</th><th>Source column</th><th>Canonical field</th><th>Type</th><th>Required</th><th>Aliases</th></tr></thead><tbody>{mappings.map((row) => <tr key={row.id}><td>{row.dataset_code}</td><td>{row.source_sheet}</td><td>{row.source_column}</td><td><code>{row.canonical_field}</code></td><td>{row.data_type}{row.unit ? ` · ${row.unit}` : ""}</td><td>{row.required ? "Yes" : "No"}</td><td>{row.aliases.join(", ") || "—"}</td></tr>)}{mappings.length === 0 && <tr><td colSpan={7}>No active mapping rows are available for this profile.</td></tr>}</tbody></table></div>
    </section>
  </div>;
}
