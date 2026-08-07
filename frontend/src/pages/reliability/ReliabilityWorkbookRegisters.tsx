import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  createWorkbookRecord,
  getOosMetrics,
  listWorkbookRecords,
  transitionWorkbookRecord,
} from "./reliabilityWorkbookParityApi";
import {
  buildRecordCreate,
  downloadText,
  formatValue,
  initialCommonDraft,
  initialPayload,
  validateRecordDraft,
  workbookRecordsCsv,
  type CommonRecordDraft,
} from "./reliabilityWorkbookParityModel";
import type {
  OosMetrics,
  WorkbookDatasetCode,
  WorkbookField,
  WorkbookFieldDefinition,
  WorkbookRecord,
  WorkbookRecordStatus,
} from "./reliabilityWorkbookParityTypes";
import { DATASET_ORDER } from "./reliabilityWorkbookParityTypes";

const PAGE_SIZE = 50;

type Props = {
  catalog: WorkbookFieldDefinition[];
  selectedDataset: WorkbookDatasetCode;
  onDatasetChange: (value: WorkbookDatasetCode) => void;
};

type Filters = {
  periodStart: string;
  periodEnd: string;
  aircraft: string;
  status: WorkbookRecordStatus | "";
  q: string;
};

const emptyFilters: Filters = { periodStart: "", periodEnd: "", aircraft: "", status: "", q: "" };

export function ReliabilityWorkbookRegisters({ catalog, selectedDataset, onDatasetChange }: Props): React.ReactElement {
  const definition = useMemo(
    () => catalog.find((item) => item.code === selectedDataset) || catalog[0],
    [catalog, selectedDataset],
  );
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(emptyFilters);
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<WorkbookRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [common, setCommon] = useState<CommonRecordDraft>(() => initialCommonDraft(definition));
  const [payload, setPayload] = useState<Record<string, string | boolean>>(() => initialPayload(definition));
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [actionNote, setActionNote] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [oosMetrics, setOosMetrics] = useState<OosMetrics | null>(null);

  const loadRecords = useCallback(async () => {
    if (!definition) return;
    setLoading(true);
    setError(null);
    try {
      const result = await listWorkbookRecords({
        datasetCode: definition.code,
        aircraft: appliedFilters.aircraft,
        status: appliedFilters.status,
        periodStart: appliedFilters.periodStart,
        periodEnd: appliedFilters.periodEnd,
        q: appliedFilters.q,
        limit: PAGE_SIZE,
        offset,
      });
      setRecords(result);
      if (definition.code === "OOS" && appliedFilters.periodStart && appliedFilters.periodEnd) {
        setOosMetrics(await getOosMetrics({
          periodStart: appliedFilters.periodStart,
          periodEnd: appliedFilters.periodEnd,
          aircraft: appliedFilters.aircraft,
        }));
      } else {
        setOosMetrics(null);
      }
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Workbook records could not be loaded.");
      setRecords([]);
      setOosMetrics(null);
    } finally {
      setLoading(false);
    }
  }, [appliedFilters, definition, offset]);

  useEffect(() => { void loadRecords(); }, [loadRecords]);

  useEffect(() => {
    setCommon(initialCommonDraft(definition));
    setPayload(initialPayload(definition));
    setFormErrors([]);
    setOffset(0);
    setExpandedId(null);
  }, [definition]);

  if (!definition) return <p className="rel-wp__empty">No workbook dataset catalogue is available.</p>;

  const submitRecord = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateRecordDraft(definition, common, payload);
    setFormErrors(errors);
    if (errors.length) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createWorkbookRecord(buildRecordCreate(definition, common, payload));
      setNotice(`${created.record_number} was saved as a controlled draft.`);
      setCommon(initialCommonDraft(definition));
      setPayload(initialPayload(definition));
      await loadRecords();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The workbook record could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const applyLifecycle = async (record: WorkbookRecord, action: "approve" | "close") => {
    const rationale = actionNote.trim();
    if (rationale.length < 2) {
      setError("Enter an approval or closure rationale of at least 2 characters before changing controlled status.");
      return;
    }
    const verb = action === "approve" ? "Approve" : "Close";
    if (!window.confirm(`${verb} ${record.record_number}? This controlled lifecycle action will be retained with your rationale.`)) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await transitionWorkbookRecord(record.id, action, rationale);
      setNotice(`${updated.record_number} is now ${updated.status.toLowerCase()}.`);
      setActionNote("");
      await loadRecords();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : `The record could not be ${action}d.`);
    } finally {
      setSaving(false);
    }
  };

  return <div className="rel-wp__registers">
    <aside className="rel-wp__dataset-rail" aria-label="Workbook datasets">
      {DATASET_ORDER.map((code) => {
        const item = catalog.find((candidate) => candidate.code === code);
        return <button
          key={code}
          type="button"
          className={code === definition.code ? "is-active" : ""}
          onClick={() => onDatasetChange(code)}
        >
          <strong>{code}</strong>
          <span>{item?.name || code}</span>
        </button>;
      })}
    </aside>

    <div className="rel-wp__register-main">
      <section className="rel-wp__panel rel-wp__dataset-intro">
        <div>
          <p className="rel-wp__eyebrow">{definition.workbook_sheet_names.join(" · ")}</p>
          <h2>{definition.name}</h2>
          <p>{definition.description}</p>
        </div>
        <div className="rel-wp__dataset-actions">
          <button type="button" className="btn btn-secondary" onClick={() => downloadText(
            `${definition.code.toLowerCase()}-register.csv`,
            workbookRecordsCsv(records, definition),
          )}>Export loaded rows</button>
          <button type="button" className="btn btn-secondary" onClick={() => void loadRecords()}>Refresh</button>
        </div>
      </section>

      {oosMetrics && <OosMetricStrip metrics={oosMetrics} />}
      {notice && <div className="rel-wp__notice" role="status">{notice}<button type="button" onClick={() => setNotice(null)}>Dismiss</button></div>}
      {error && <div className="rel-wp__error" role="alert">{error}</div>}

      <section className="rel-wp__panel">
        <div className="rel-wp__section-heading">
          <div><p className="rel-wp__eyebrow">Controlled source entry</p><h3>Create {definition.code} record</h3></div>
          <span>{definition.fields.filter((field) => field.required).length} dataset fields required</span>
        </div>
        <form className="rel-wp__form" onSubmit={submitRecord}>
          <div className="rel-wp__form-grid rel-wp__form-grid--common">
            <label>Event date<input type="date" required value={common.eventDate} onChange={(event) => setCommon({ ...common, eventDate: event.target.value })} /></label>
            <label>Event end date<input type="date" value={common.eventEndDate} onChange={(event) => setCommon({ ...common, eventEndDate: event.target.value })} /></label>
            <label>Aircraft serial number<input value={common.aircraft} onChange={(event) => setCommon({ ...common, aircraft: event.target.value })} placeholder="5Y-… or serial number" /></label>
            <label>ATA chapter<input value={common.ataChapter} onChange={(event) => setCommon({ ...common, ataChapter: event.target.value })} placeholder="e.g. 32" /></label>
            <label>Reference code<input value={common.referenceCode} onChange={(event) => setCommon({ ...common, referenceCode: event.target.value })} /></label>
            <label className="rel-wp__span-2">Record title<input required value={common.title} onChange={(event) => setCommon({ ...common, title: event.target.value })} /></label>
            <label className="rel-wp__span-2">Description<textarea rows={3} value={common.description} onChange={(event) => setCommon({ ...common, description: event.target.value })} /></label>
          </div>

          <fieldset>
            <legend>{definition.name} fields</legend>
            <div className="rel-wp__form-grid">
              {definition.fields.map((field) => <DynamicField
                key={field.key}
                field={field}
                value={payload[field.key] ?? (field.data_type === "boolean" ? false : "")}
                onChange={(value) => setPayload((current) => ({ ...current, [field.key]: value }))}
              />)}
            </div>
          </fieldset>

          <details className="rel-wp__source-provenance">
            <summary>Historical workbook provenance</summary>
            <div className="rel-wp__form-grid">
              <label>Source workbook<input value={common.sourceWorkbook} onChange={(event) => setCommon({ ...common, sourceWorkbook: event.target.value })} /></label>
              <label>Source sheet<input value={common.sourceSheet} onChange={(event) => setCommon({ ...common, sourceSheet: event.target.value })} /></label>
              <label>Source row<input type="number" min="1" value={common.sourceRowNumber} onChange={(event) => setCommon({ ...common, sourceRowNumber: event.target.value })} /></label>
            </div>
          </details>

          {formErrors.length > 0 && <div className="rel-wp__validation" role="alert"><strong>Complete the required evidence:</strong><ul>{formErrors.map((item) => <li key={item}>{item}</li>)}</ul></div>}
          <div className="rel-wp__form-actions"><button className="btn btn-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save controlled draft"}</button></div>
        </form>
      </section>

      <section className="rel-wp__panel">
        <div className="rel-wp__section-heading">
          <div><p className="rel-wp__eyebrow">Server-bounded register</p><h3>{definition.code} records</h3></div>
          <span>{offset + 1}–{offset + records.length}</span>
        </div>
        <div className="rel-wp__filters">
          <label>From<input type="date" value={filters.periodStart} onChange={(event) => setFilters({ ...filters, periodStart: event.target.value })} /></label>
          <label>To<input type="date" value={filters.periodEnd} onChange={(event) => setFilters({ ...filters, periodEnd: event.target.value })} /></label>
          <label>Aircraft<input value={filters.aircraft} onChange={(event) => setFilters({ ...filters, aircraft: event.target.value })} /></label>
          <label>Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value as Filters["status"] })}><option value="">All</option><option>DRAFT</option><option>APPROVED</option><option>CLOSED</option><option>REJECTED</option></select></label>
          <label className="rel-wp__filter-search">Search<input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} placeholder="Record, reference, title, aircraft" /></label>
          <button type="button" className="btn btn-primary" onClick={() => { setOffset(0); setAppliedFilters(filters); }}>Apply</button>
          <button type="button" className="btn btn-secondary" onClick={() => { setFilters(emptyFilters); setAppliedFilters(emptyFilters); setOffset(0); }}>Reset</button>
        </div>

        <div className="rel-wp__lifecycle-note"><label>Approval or closure rationale *<input minLength={2} value={actionNote} onChange={(event) => setActionNote(event.target.value)} placeholder="Required before approval or closure" /><small>At least 2 characters. The rationale is retained with the controlled lifecycle action.</small></label></div>
        <div className="rel-wp__table-wrap">
          <table className="rel-wp__table">
            <thead><tr><th>Record</th><th>Date</th><th>Aircraft</th><th>ATA</th><th>Status</th><th>Title</th><th>Derived</th><th>Control</th></tr></thead>
            <tbody>
              {records.map((record) => <React.Fragment key={record.id}>
                <tr>
                  <td><button type="button" className="rel-wp__link-button" onClick={() => setExpandedId(expandedId === record.id ? null : record.id)}>{record.record_number}</button></td>
                  <td>{record.event_date}</td>
                  <td>{record.aircraft_serial_number || "Fleet"}</td>
                  <td>{record.ata_chapter || "—"}</td>
                  <td><span className={`rel-wp__status rel-wp__status--${record.status.toLowerCase()}`}>{record.status}</span></td>
                  <td>{record.title}</td>
                  <td>{Object.keys(record.derived_values || {}).length ? Object.entries(record.derived_values).slice(0, 2).map(([key, value]) => <span className="rel-wp__derived" key={key}>{key.replaceAll("_", " ")}: {formatValue(value)}</span>) : "—"}</td>
                  <td><div className="rel-wp__row-actions">
                    {record.status === "DRAFT" && <button type="button" onClick={() => void applyLifecycle(record, "approve")} disabled={saving}>Approve</button>}
                    {record.status === "APPROVED" && <button type="button" onClick={() => void applyLifecycle(record, "close")} disabled={saving}>Close</button>}
                    {record.canonical_event_id && <span title="Canonical Reliability event created">Event #{record.canonical_event_id}</span>}
                  </div></td>
                </tr>
                {expandedId === record.id && <tr className="rel-wp__detail-row"><td colSpan={8}><RecordDetail record={record} definition={definition} /></td></tr>}
              </React.Fragment>)}
              {!loading && records.length === 0 && <tr><td colSpan={8}>No records match the selected filters.</td></tr>}
              {loading && <tr><td colSpan={8}>Loading controlled records…</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="rel-wp__pagination">
          <button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <span>Page {Math.floor(offset / PAGE_SIZE) + 1}</span>
          <button type="button" disabled={records.length < PAGE_SIZE || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </div>
      </section>
    </div>
  </div>;
}

function DynamicField({ field, value, onChange }: { field: WorkbookField; value: string | boolean; onChange: (value: string | boolean) => void }): React.ReactElement {
  const required = field.required;
  const caption = <>{field.label}{field.unit ? ` (${field.unit})` : ""}{required ? <span aria-hidden="true"> *</span> : null}</>;
  if (field.data_type === "boolean") {
    return <label className="rel-wp__checkbox"><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />{caption}{field.help_text && <small>{field.help_text}</small>}</label>;
  }
  if (field.data_type === "textarea") {
    return <label className="rel-wp__span-2">{caption}<textarea rows={3} required={required} value={String(value)} onChange={(event) => onChange(event.target.value)} />{field.help_text && <small>{field.help_text}</small>}</label>;
  }
  if (field.data_type === "select") {
    return <label>{caption}<select required={required} value={String(value)} onChange={(event) => onChange(event.target.value)}><option value="">Select…</option>{field.options.map((option) => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}</select>{field.help_text && <small>{field.help_text}</small>}</label>;
  }
  const inputType = field.data_type === "date" ? "date" : field.data_type === "datetime" ? "datetime-local" : ["decimal", "integer"].includes(field.data_type) ? "number" : "text";
  return <label>{caption}<input type={inputType} step={field.data_type === "decimal" ? "any" : undefined} required={required} value={String(value)} onChange={(event) => onChange(event.target.value)} />{field.help_text && <small>{field.help_text}</small>}</label>;
}

function RecordDetail({ record, definition }: { record: WorkbookRecord; definition: WorkbookFieldDefinition }): React.ReactElement {
  return <div className="rel-wp__record-detail">
    <div><h4>Controlled payload</h4><dl>{definition.fields.map((field) => <React.Fragment key={field.key}><dt>{field.label}</dt><dd>{formatValue(record.payload[field.key])}</dd></React.Fragment>)}</dl></div>
    <div><h4>Derived and provenance</h4><dl>
      {Object.entries(record.derived_values || {}).map(([key, value]) => <React.Fragment key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{formatValue(value)}</dd></React.Fragment>)}
      <dt>Source workbook</dt><dd>{record.source_workbook || "Native portal entry"}</dd>
      <dt>Source sheet / row</dt><dd>{record.source_sheet || "—"}{record.source_row_number ? ` / ${record.source_row_number}` : ""}</dd>
      <dt>Revision</dt><dd>{record.revision}</dd>
      <dt>Updated</dt><dd>{new Date(record.updated_at).toLocaleString()}</dd>
    </dl></div>
  </div>;
}

function OosMetricStrip({ metrics }: { metrics: OosMetrics }): React.ReactElement {
  const values: Array<[string, string]> = [
    ["OOS occurrences", String(metrics.records)],
    ["Downtime", `${metrics.downtime_hours.toFixed(2)} h`],
    ["Scheduled availability", `${metrics.scheduled_available_hours.toFixed(2)} h`],
    ["Available time", `${metrics.available_hours.toFixed(2)} h`],
    ["Availability", metrics.availability_pct == null ? "Withheld" : `${metrics.availability_pct.toFixed(2)}%`],
    ["MTTR", metrics.mttr_hours == null ? "Withheld" : `${metrics.mttr_hours.toFixed(2)} h`],
  ];
  return <section className="rel-wp__metric-strip">{values.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</section>;
}
