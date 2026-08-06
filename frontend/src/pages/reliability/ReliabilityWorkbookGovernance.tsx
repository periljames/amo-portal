import React, { useMemo, useState } from "react";

import { apiRequest } from "../../services/apiClient";
import type { AircraftRead } from "../../services/fleet";
import type {
  DatasetDefinition,
  MappingSeedResult,
  ParityRow,
  ReportLayout,
  ReportSnapshot,
  WorkbookDatasetCode,
} from "./reliabilityWorkbookParityTypes";

type MappingProps = {
  catalog: DatasetDefinition[];
  parity: ParityRow[];
  loading: boolean;
  reload: () => Promise<void>;
};

type ReportProps = {
  catalog: DatasetDefinition[];
  aircraft: AircraftRead[];
  layouts: ReportLayout[];
  reports: ReportSnapshot[];
  loading: boolean;
  reload: () => Promise<void>;
};

function defaultStart(): string {
  const date = new Date();
  date.setMonth(date.getMonth() - 1);
  return date.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function saveHtml(content: string, filename: string): void {
  const blob = new Blob([content], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function ReliabilityWorkbookMappingGovernance({ catalog, parity, loading, reload }: MappingProps): React.ReactElement {
  const [seeding, setSeeding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profileCode, setProfileCode] = useState("OPERATOR-CUSTOM");
  const [profileName, setProfileName] = useState("Operator custom Reliability workbook");
  const [workbookFamily, setWorkbookFamily] = useState("OPERATOR");
  const [datasetCode, setDatasetCode] = useState<WorkbookDatasetCode>("AU");
  const [sourceSheet, setSourceSheet] = useState("AU");
  const [sourceColumn, setSourceColumn] = useState("");
  const [canonicalField, setCanonicalField] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const definition = useMemo(() => catalog.find((item) => item.code === datasetCode), [catalog, datasetCode]);
  const selectedField = definition?.fields.find((field) => field.key === canonicalField);

  const seed = async () => {
    setSeeding(true);
    setError(null);
    try {
      const result = await apiRequest<MappingSeedResult>("/reliability/workbook-parity/mappings/seed-defaults", { method: "POST", cacheTtlMs: 0 });
      setSuccess(`${result.created} mapping rows created, ${result.repaired} repaired; ${result.total_active} active across ${result.profiles.length} profiles.`);
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Default workbook mappings could not be configured.");
    } finally {
      setSeeding(false);
    }
  };

  const saveMapping = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedField) return;
    setSaving(true);
    setError(null);
    try {
      await apiRequest("/reliability/workbook-parity/mappings", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          profile_code: profileCode.trim().toUpperCase(),
          profile_name: profileName.trim(),
          workbook_family: workbookFamily.trim().toUpperCase(),
          dataset_code: datasetCode,
          source_sheet: sourceSheet.trim(),
          source_column: sourceColumn.trim(),
          canonical_field: selectedField.key,
          data_type: selectedField.data_type,
          required: selectedField.required,
          unit: selectedField.unit || null,
          aliases: [sourceColumn.trim(), selectedField.label, selectedField.key].filter(Boolean),
          transform: {
            trim: ["text", "textarea", "select"].includes(selectedField.data_type),
            uppercase: selectedField.data_type === "select",
            exact_numeric: ["decimal", "integer"].includes(selectedField.data_type),
          },
        }),
        cacheTtlMs: 0,
      });
      setSuccess(`${sourceSheet}.${sourceColumn} mapped to ${datasetCode}.${selectedField.key}.`);
      setSourceColumn("");
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The workbook field mapping could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  return <>
    <section className="rel-wb__intro">
      <div><p className="reliability-v2__eyebrow">Formal workbook-to-database control</p><h2>Field mapping and parity</h2><p>Every workbook family maps explicit source sheets and columns to a typed canonical field. Required-field gaps remain visible and prevent an unsupported full-parity claim.</p></div>
      <button type="button" className="btn btn-primary" onClick={() => void seed()} disabled={seeding}>{seeding ? "Configuring mappings…" : "Configure default C208B, DHC8 and generic mappings"}</button>
    </section>
    {error && <div className="reliability-v2__error" role="alert">{error}</div>}
    {success && <div className="rel-wb__success" role="status">{success}</div>}

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Live parity matrix</p><h3>Required and optional field coverage</h3></div><span>{parity.length} datasets</span></div>
      {loading ? <div className="reliability-v2__loading">Loading parity evidence…</div> : <div className="rel-wb__table-wrap"><table className="rel-wb__table"><thead><tr><th>Dataset</th><th>Required</th><th>Optional</th><th>Mapped required</th><th>Missing required</th><th>Coverage</th><th>Records</th></tr></thead><tbody>{parity.map((row) => <tr key={row.dataset_code}><td><strong>{row.dataset_code} · {row.dataset_name}</strong></td><td>{row.required_fields.length}</td><td>{row.optional_fields.length}</td><td>{row.mapped_required_fields.length}</td><td>{row.missing_required_fields.length ? <span className="rel-wb__missing">{row.missing_required_fields.join(", ")}</span> : <span className="rel-wb__complete">Complete</span>}</td><td><progress max={100} value={row.coverage_pct} /> <span>{row.coverage_pct.toFixed(1)}%</span></td><td>{row.record_count}</td></tr>)}{parity.length === 0 && <tr><td colSpan={7}>Configure the default mappings to establish the parity matrix.</td></tr>}</tbody></table></div>}
    </section>

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Operator extension</p><h3>Add a controlled source-column mapping</h3></div><span>No raw JSON required</span></div>
      <form className="rel-wb__form" onSubmit={saveMapping}>
        <div className="rel-wb__form-grid">
          <label><span>Profile code *</span><input required value={profileCode} onChange={(event) => setProfileCode(event.target.value)} /></label>
          <label><span>Profile name *</span><input required value={profileName} onChange={(event) => setProfileName(event.target.value)} /></label>
          <label><span>Workbook family *</span><input required value={workbookFamily} onChange={(event) => setWorkbookFamily(event.target.value)} /></label>
          <label><span>Dataset *</span><select value={datasetCode} onChange={(event) => { const next = event.target.value as WorkbookDatasetCode; setDatasetCode(next); setCanonicalField(""); setSourceSheet(catalog.find((item) => item.code === next)?.workbook_sheet_names[0] || next); }}>{catalog.map((item) => <option value={item.code} key={item.code}>{item.code} · {item.name}</option>)}</select></label>
          <label><span>Source sheet *</span><input required value={sourceSheet} onChange={(event) => setSourceSheet(event.target.value)} /></label>
          <label><span>Source column *</span><input required value={sourceColumn} onChange={(event) => setSourceColumn(event.target.value)} placeholder="Exact workbook header" /></label>
          <label><span>Canonical field *</span><select required value={canonicalField} onChange={(event) => setCanonicalField(event.target.value)}><option value="">Select field</option>{definition?.fields.map((field) => <option value={field.key} key={field.key}>{field.label}{field.required ? " *" : ""}</option>)}</select></label>
          <label><span>Data type / unit</span><input readOnly value={selectedField ? `${selectedField.data_type}${selectedField.unit ? ` · ${selectedField.unit}` : ""}` : "Select a field"} /></label>
        </div>
        <div className="rel-wb__form-actions"><button className="btn btn-primary" type="submit" disabled={saving || !selectedField}>{saving ? "Saving controlled mapping…" : "Add mapping"}</button></div>
      </form>
    </section>
  </>;
}

export function ReliabilityWorkbookReportGovernance({ catalog, aircraft, layouts, reports, loading, reload }: ReportProps): React.ReactElement {
  const [layoutId, setLayoutId] = useState("");
  const [periodStart, setPeriodStart] = useState(defaultStart());
  const [periodEnd, setPeriodEnd] = useState(today());
  const [aircraftFilter, setAircraftFilter] = useState<string[]>([]);
  const [seeding, setSeeding] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [layoutCode, setLayoutCode] = useState("OPERATOR-RP-CUSTOM");
  const [layoutName, setLayoutName] = useState("Operator Reliability Programme Report");
  const [aircraftFamily, setAircraftFamily] = useState("OPERATOR");
  const [selectedDatasets, setSelectedDatasets] = useState<WorkbookDatasetCode[]>(catalog.map((item) => item.code));
  const [includeEvents, setIncludeEvents] = useState(true);
  const [includeAlerts, setIncludeAlerts] = useState(true);
  const [savingLayout, setSavingLayout] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const activeLayouts = layouts.filter((layout) => layout.active);
  const effectiveLayoutId = layoutId || String(activeLayouts[0]?.id || "");

  const seedLayouts = async () => {
    setSeeding(true);
    setError(null);
    try {
      await apiRequest("/reliability/workbook-parity/report-layouts/seed", { method: "POST", cacheTtlMs: 0 });
      setSuccess("C208B, DHC8 and operator report layouts configured idempotently.");
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Default report layouts could not be configured.");
    } finally {
      setSeeding(false);
    }
  };

  const saveLayout = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingLayout(true);
    setError(null);
    try {
      const sections: Array<Record<string, unknown>> = [
        { code: "EXECUTIVE", title: "Executive summary", kind: "SUMMARY" },
        ...(includeEvents ? [{ code: "EVENTS", title: "Operational interruptions", kind: "EVENTS" }] : []),
        ...selectedDatasets.map((code) => ({ code, title: catalog.find((item) => item.code === code)?.name || code, kind: "DATASET", dataset_code: code })),
        ...(includeAlerts ? [{ code: "ALERTS", title: "Statistical alert calculations", kind: "STATISTICAL_ALERTS" }] : []),
      ];
      const created = await apiRequest<ReportLayout>("/reliability/workbook-parity/report-layouts", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ code: layoutCode.trim().toUpperCase(), name: layoutName.trim(), aircraft_family: aircraftFamily.trim().toUpperCase(), sections, page_settings: { size: "A4", orientation: "portrait", margin_mm: 10 } }),
        cacheTtlMs: 0,
      });
      setLayoutId(String(created.id));
      setSuccess(`${created.name} revision ${created.revision} created and made effective.`);
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The report layout revision could not be created.");
    } finally {
      setSavingLayout(false);
    }
  };

  const render = async () => {
    if (!effectiveLayoutId) {
      setError("Configure or select a report layout first.");
      return;
    }
    setRendering(true);
    setError(null);
    try {
      const created = await apiRequest<ReportSnapshot>("/reliability/workbook-parity/reports/render", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ layout_id: Number(effectiveLayoutId), period_start: periodStart, period_end: periodEnd, aircraft: aircraftFilter }),
        cacheTtlMs: 0,
      });
      setSuccess(`Controlled report snapshot #${created.id} generated with SHA-256 ${created.sha256_hash.slice(0, 12)}…`);
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The controlled report could not be generated.");
    } finally {
      setRendering(false);
    }
  };

  const download = async (report: ReportSnapshot) => {
    setDownloading(report.id);
    setError(null);
    try {
      const content = await apiRequest<string>(report.download_url, { cacheTtlMs: 0 });
      saveHtml(content, `${report.layout_code.toLowerCase()}-${report.period_start}-${report.period_end}.html`);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The retained report could not be downloaded.");
    } finally {
      setDownloading(null);
    }
  };

  const toggleDataset = (code: WorkbookDatasetCode) => {
    setSelectedDatasets((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
  };

  return <>
    <section className="rel-wb__intro">
      <div><p className="reliability-v2__eyebrow">Controlled retained output</p><h2>Reliability programme report layouts</h2><p>Generate C208B, DHC8 or operator-specific reports from approved source records and retained statistical calculations. Layout revisions are immutable and each output receives a SHA-256 evidence hash.</p></div>
      <button type="button" className="btn btn-primary" disabled={seeding} onClick={() => void seedLayouts()}>{seeding ? "Configuring layouts…" : "Configure default layouts"}</button>
    </section>
    {error && <div className="reliability-v2__error" role="alert">{error}</div>}
    {success && <div className="rel-wb__success" role="status">{success}</div>}

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">New layout revision</p><h3>Configure operator report content</h3></div><span>A4 portrait controlled layout</span></div>
      <form className="rel-wb__form" onSubmit={saveLayout}>
        <div className="rel-wb__form-grid">
          <label><span>Layout code *</span><input required value={layoutCode} onChange={(event) => setLayoutCode(event.target.value)} /></label>
          <label><span>Layout name *</span><input required value={layoutName} onChange={(event) => setLayoutName(event.target.value)} /></label>
          <label><span>Aircraft family *</span><input required value={aircraftFamily} onChange={(event) => setAircraftFamily(event.target.value)} /></label>
        </div>
        <fieldset className="rel-wb__fieldset"><legend>Report sections</legend><label><input type="checkbox" checked={includeEvents} onChange={(event) => setIncludeEvents(event.target.checked)} />Canonical operational interruptions</label>{catalog.map((item) => <label key={item.code}><input type="checkbox" checked={selectedDatasets.includes(item.code)} onChange={() => toggleDataset(item.code)} />{item.code} · {item.name}</label>)}<label><input type="checkbox" checked={includeAlerts} onChange={(event) => setIncludeAlerts(event.target.checked)} />Statistical alert calculations</label></fieldset>
        <div className="rel-wb__form-actions"><button className="btn btn-primary" type="submit" disabled={savingLayout || selectedDatasets.length === 0}>{savingLayout ? "Creating revision…" : "Create layout revision"}</button></div>
      </form>
    </section>

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Generate evidence</p><h3>Render controlled Reliability report</h3></div><span>{activeLayouts.length} effective layouts</span></div>
      <div className="rel-wb__form-grid">
        <label><span>Report layout *</span><select value={effectiveLayoutId} onChange={(event) => setLayoutId(event.target.value)}><option value="">Configure a layout</option>{activeLayouts.map((layout) => <option value={layout.id} key={layout.id}>{layout.code} · {layout.name} · rev {layout.revision}</option>)}</select></label>
        <label><span>Period start *</span><input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
        <label><span>Period end *</span><input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
        <label className="rel-wb__span-2"><span>Aircraft filter</span><select multiple value={aircraftFilter} onChange={(event) => setAircraftFilter(Array.from(event.target.selectedOptions).map((option) => option.value))}>{aircraft.map((item) => <option value={item.serial_number} key={item.serial_number}>{item.registration || item.serial_number} · {item.serial_number}</option>)}</select><small>Leave unselected for the full fleet.</small></label>
      </div>
      <div className="rel-wb__form-actions"><button type="button" className="btn btn-primary" onClick={() => void render()} disabled={rendering || !effectiveLayoutId}>{rendering ? "Rendering and hashing evidence…" : "Generate controlled report"}</button></div>
    </section>

    <section className="rel-wb__panel">
      <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Retained report register</p><h3>Generated Reliability programme reports</h3></div><span>{reports.length} loaded</span></div>
      {loading ? <div className="reliability-v2__loading">Loading report evidence…</div> : <div className="rel-wb__table-wrap"><table className="rel-wb__table"><thead><tr><th>Report</th><th>Period</th><th>Aircraft scope</th><th>Evidence hash</th><th>Generated</th><th>Output</th></tr></thead><tbody>{reports.map((report) => <tr key={report.id}><td><strong>{report.layout_name || report.layout_code}</strong><span>Snapshot #{report.id}</span></td><td>{report.period_start} → {report.period_end}</td><td>{report.aircraft.length ? report.aircraft.join(", ") : "Full fleet"}</td><td><code>{report.sha256_hash.slice(0, 16)}…</code></td><td>{new Date(report.generated_at).toLocaleString()}</td><td><button type="button" className="btn btn-secondary" disabled={downloading === report.id} onClick={() => void download(report)}>{downloading === report.id ? "Downloading…" : "Download HTML / print PDF"}</button></td></tr>)}{reports.length === 0 && <tr><td colSpan={6}>No controlled workbook-parity reports have been generated.</td></tr>}</tbody></table></div>}
    </section>
  </>;
}
