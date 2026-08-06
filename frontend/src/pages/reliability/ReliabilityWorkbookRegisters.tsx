import React, { useEffect, useMemo, useState } from "react";

import { apiRequest } from "../../services/apiClient";
import type { AircraftRead } from "../../services/fleet";
import type {
  DatasetDefinition,
  FieldDefinition,
  OosMetrics,
  WorkbookDatasetCode,
  WorkbookRecord,
} from "./reliabilityWorkbookParityTypes";

type Props = {
  catalog: DatasetDefinition[];
  aircraft: AircraftRead[];
  activeDataset: WorkbookDatasetCode;
  setActiveDataset: (value: WorkbookDatasetCode) => void;
  records: WorkbookRecord[];
  loading: boolean;
  page: number;
  setPage: (value: number) => void;
  reload: () => Promise<void>;
  oosMetrics: OosMetrics | null;
};

type ActionState = { record: WorkbookRecord; kind: "approve" | "close" } | null;

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function initialPayload(definition?: DatasetDefinition): Record<string, unknown> {
  return Object.fromEntries((definition?.fields || []).map((field) => [field.key, field.data_type === "boolean" ? false : ""]));
}

function datetimeValue(value: unknown): string {
  if (!value) return "";
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusClass(value: string): string {
  return `reliability-v2__status reliability-v2__status--${value.toLowerCase().replaceAll("_", "-")}`;
}

function fieldValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function payloadSummary(record: WorkbookRecord, definition?: DatasetDefinition): Array<[string, string]> {
  const fields = definition?.fields || [];
  const preferred = fields.filter((field) => record.payload[field.key] not in [undefined]);
  const populated = preferred.filter((field) => record.payload[field.key] != null && record.payload[field.key] !== "").slice(0, 3);
  return populated.map((field) => [field.label, fieldValue(record.payload[field.key])]);
}

function normalizePayload(definition: DatasetDefinition, payload: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of definition.fields) {
    const raw = payload[field.key];
    if (field.data_type === "boolean") {
      result[field.key] = Boolean(raw);
    } else if (field.data_type === "datetime" && raw) {
      result[field.key] = new Date(String(raw)).toISOString();
    } else if (raw !== "" && raw != null) {
      result[field.key] = raw;
    }
  }
  return result;
}

export function ReliabilityWorkbookRegisters({ catalog, aircraft, activeDataset, setActiveDataset, records, loading, page, setPage, reload, oosMetrics }: Props): React.ReactElement {
  const definition = useMemo(() => catalog.find((item) => item.code === activeDataset), [activeDataset, catalog]);
  const [eventDate, setEventDate] = useState(today());
  const [aircraftSerial, setAircraftSerial] = useState("");
  const [ataChapter, setAtaChapter] = useState("");
  const [referenceCode, setReferenceCode] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sourceWorkbook, setSourceWorkbook] = useState("");
  const [sourceSheet, setSourceSheet] = useState("");
  const [sourceRow, setSourceRow] = useState("");
  const [payload, setPayload] = useState<Record<string, unknown>>(() => initialPayload(definition));
  const [submitting, setSubmitting] = useState(false);
  const [action, setAction] = useState<ActionState>(null);
  const [actionNote, setActionNote] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    setPayload(initialPayload(definition));
    setSourceSheet(definition?.workbook_sheet_names[0] || "");
    setTitle("");
    setDescription("");
    setReferenceCode("");
    setAtaChapter("");
    setPage(0);
    setError(null);
    setSuccess(null);
  }, [definition, setPage]);

  const updatePayload = (field: FieldDefinition, value: unknown) => {
    setPayload((current) => ({ ...current, [field.key]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!definition) return;
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await apiRequest<WorkbookRecord>("/reliability/workbook-parity/records", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          dataset_code: activeDataset,
          event_date: eventDate,
          aircraft_serial_number: aircraftSerial || null,
          ata_chapter: ataChapter.trim() || null,
          reference_code: referenceCode.trim() || null,
          title: title.trim(),
          description: description.trim() || null,
          payload: normalizePayload(definition, payload),
          source_workbook: sourceWorkbook.trim() || null,
          source_sheet: sourceSheet.trim() || null,
          source_row_number: sourceRow ? Number(sourceRow) : null,
        }),
        cacheTtlMs: 0,
      });
      setPayload(initialPayload(definition));
      setTitle("");
      setDescription("");
      setReferenceCode("");
      setSourceRow("");
      setSuccess(`${definition.name} draft created. Review and approve it from the register below.`);
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The Reliability workbook record could not be created.");
    } finally {
      setSubmitting(false);
    }
  };

  const runAction = async () => {
    if (!action || !actionNote.trim()) return;
    setActionLoading(true);
    setError(null);
    try {
      await apiRequest<WorkbookRecord>(`/reliability/workbook-parity/records/${action.record.id}/${action.kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ note: actionNote.trim() }),
        cacheTtlMs: 0,
      });
      setSuccess(`${action.record.record_number} ${action.kind === "approve" ? "approved and linked to authoritative Reliability evidence" : "closed"}.`);
      setAction(null);
      setActionNote("");
      await reload();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The controlled lifecycle action failed.");
    } finally {
      setActionLoading(false);
    }
  };

  return <>
    <nav className="rel-wb__dataset-nav" aria-label="Reliability workbook registers">
      {catalog.map((item) => <button type="button" key={item.code} className={item.code === activeDataset ? "is-active" : ""} onClick={() => setActiveDataset(item.code)}>
        <strong>{item.code}</strong><span>{item.name}</span>
      </button>)}
    </nav>

    {definition && <>
      <section className="rel-wb__intro">
        <div><p className="reliability-v2__eyebrow">Controlled source register</p><h2>{definition.name}</h2><p>{definition.description}</p></div>
        <div className="rel-wb__sheet-tags">{definition.workbook_sheet_names.map((name) => <span key={name}>{name}</span>)}</div>
      </section>

      {activeDataset === "OOS" && oosMetrics && <section className="rel-wb__metrics" aria-label="Out-of-service metrics">
        <Metric label="OOS records" value={String(oosMetrics.records)} />
        <Metric label="Downtime" value={`${oosMetrics.downtime_hours.toFixed(2)} h`} />
        <Metric label="Availability" value={oosMetrics.availability_pct == null ? "No exposure" : `${oosMetrics.availability_pct.toFixed(2)}%`} />
        <Metric label="MTTR" value={oosMetrics.mttr_hours == null ? "No closed intervals" : `${oosMetrics.mttr_hours.toFixed(2)} h`} />
      </section>}

      {error && <div className="reliability-v2__error" role="alert">{error}</div>}
      {success && <div className="rel-wb__success" role="status">{success}</div>}

      <section className="rel-wb__panel">
        <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">New controlled record</p><h3>Capture {definition.name.toLowerCase()}</h3></div><span>Draft → approval → canonical evidence → closure</span></div>
        <form onSubmit={submit} className="rel-wb__form">
          <div className="rel-wb__form-grid rel-wb__form-grid--common">
            <label><span>Event / measurement date *</span><input type="date" required value={eventDate} onChange={(event) => setEventDate(event.target.value)} /></label>
            <label><span>Aircraft {activeDataset === "AI" ? "" : "*"}</span><select required={activeDataset !== "AI"} value={aircraftSerial} onChange={(event) => setAircraftSerial(event.target.value)}><option value="">{activeDataset === "AI" ? "Fleet / not allocated" : "Select active aircraft"}</option>{aircraft.map((item) => <option key={item.serial_number} value={item.serial_number}>{item.registration || item.serial_number} · {item.serial_number}</option>)}</select></label>
            <label><span>ATA chapter</span><input value={ataChapter} onChange={(event) => setAtaChapter(event.target.value)} placeholder="e.g. 21" maxLength={20} /></label>
            <label><span>Source reference</span><input value={referenceCode} onChange={(event) => setReferenceCode(event.target.value)} placeholder="Technical log, WO, report or check reference" maxLength={128} /></label>
            <label className="rel-wb__span-2"><span>Record title *</span><input required minLength={2} value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`Concise ${definition.name.toLowerCase()} description`} /></label>
            <label className="rel-wb__span-2"><span>Additional narrative</span><textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          </div>

          <div className="rel-wb__form-grid">
            {definition.fields.map((field) => <DynamicField key={field.key} field={field} value={payload[field.key]} onChange={(value) => updatePayload(field, value)} />)}
          </div>

          <details className="rel-wb__provenance"><summary>Historical workbook provenance</summary><div className="rel-wb__form-grid">
            <label><span>Workbook filename</span><input value={sourceWorkbook} onChange={(event) => setSourceWorkbook(event.target.value)} placeholder="e.g. DHC8 RELIABILITY PROGRAMME.xlsm" /></label>
            <label><span>Source sheet</span><input value={sourceSheet} onChange={(event) => setSourceSheet(event.target.value)} /></label>
            <label><span>Source row</span><input type="number" min={1} value={sourceRow} onChange={(event) => setSourceRow(event.target.value)} /></label>
          </div></details>
          <div className="rel-wb__form-actions"><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? "Creating controlled draft…" : "Create draft record"}</button></div>
        </form>
      </section>

      <section className="rel-wb__panel">
        <div className="rel-wb__panel-heading"><div><p className="reliability-v2__eyebrow">Bounded source evidence</p><h3>{definition.name} register</h3></div><span>Page {page + 1} · up to 50 records</span></div>
        {loading ? <div className="reliability-v2__loading" role="status">Loading controlled records…</div> : <div className="rel-wb__table-wrap"><table className="rel-wb__table"><thead><tr><th>Date / record</th><th>Aircraft / ATA</th><th>Evidence summary</th><th>Status</th><th>Provenance</th><th>Actions</th></tr></thead><tbody>
          {records.map((record) => <tr key={record.id}>
            <td><strong>{record.record_number}</strong><span>{record.event_date}</span><small>Revision {record.revision}</small></td>
            <td><strong>{record.aircraft_serial_number || "Fleet"}</strong><span>{record.ata_chapter ? `ATA ${record.ata_chapter}` : "ATA unallocated"}</span></td>
            <td><strong>{record.title}</strong>{payloadSummary(record, definition).map(([label, value]) => <span key={label}><b>{label}:</b> {value}</span>)}</td>
            <td><span className={statusClass(record.status)}>{record.status}</span>{record.canonical_event_id && <small>Event #{record.canonical_event_id}</small>}</td>
            <td><span>{record.reference_code || "No source reference"}</span><small>{record.source_workbook ? `${record.source_workbook} · ${record.source_sheet || "sheet"}${record.source_row_number ? ` · row ${record.source_row_number}` : ""}` : "Portal-created record"}</small></td>
            <td><div className="rel-wb__row-actions">{record.status === "DRAFT" && <button type="button" className="btn btn-primary" onClick={() => { setAction({ record, kind: "approve" }); setActionNote(""); }}>Approve</button>}{record.status === "APPROVED" && <button type="button" className="btn btn-secondary" onClick={() => { setAction({ record, kind: "close" }); setActionNote(""); }}>Close</button>}</div></td>
          </tr>)}
          {records.length === 0 && <tr><td colSpan={6}>No {definition.name.toLowerCase()} records match this page.</td></tr>}
        </tbody></table></div>}
        <div className="rel-wb__pagination"><button type="button" className="btn btn-secondary" disabled={page === 0 || loading} onClick={() => setPage(Math.max(0, page - 1))}>Previous</button><span>Records {page * 50 + 1}–{page * 50 + records.length}</span><button type="button" className="btn btn-secondary" disabled={records.length < 50 || loading} onClick={() => setPage(page + 1)}>Next</button></div>
      </section>
    </>}

    {action && <div className="rel-wb__modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !actionLoading) setAction(null); }}>
      <section className="rel-wb__modal" role="dialog" aria-modal="true" aria-labelledby="rel-wb-action-title">
        <div><p className="reliability-v2__eyebrow">Controlled lifecycle action</p><h3 id="rel-wb-action-title">{action.kind === "approve" ? "Approve and ingest" : "Close record"}</h3><p><strong>{action.record.record_number}</strong> — {action.record.title}</p></div>
        <label><span>{action.kind === "approve" ? "Approval basis / evidence note" : "Closure evidence / reference"} *</span><textarea rows={5} required value={actionNote} onChange={(event) => setActionNote(event.target.value)} autoFocus /></label>
        <div className="rel-wb__form-actions"><button type="button" className="btn btn-secondary" disabled={actionLoading} onClick={() => setAction(null)}>Cancel</button><button type="button" className="btn btn-primary" disabled={actionLoading || actionNote.trim().length < 2} onClick={() => void runAction()}>{actionLoading ? "Applying…" : action.kind === "approve" ? "Approve record" : "Close record"}</button></div>
      </section>
    </div>}
  </>;
}

function DynamicField({ field, value, onChange }: { field: FieldDefinition; value: unknown; onChange: (value: unknown) => void }): React.ReactElement {
  const label = <span>{field.label}{field.required ? " *" : ""}{field.unit ? <em>{field.unit}</em> : null}</span>;
  if (field.data_type === "textarea") return <label className="rel-wb__span-2">{label}<textarea rows={3} required={field.required} value={String(value || "")} onChange={(event) => onChange(event.target.value)} /></label>;
  if (field.data_type === "select") return <label>{label}<select required={field.required} value={String(value || "")} onChange={(event) => onChange(event.target.value)}><option value="">Select</option>{field.options.map((option) => <option value={option} key={option}>{option.replaceAll("_", " ")}</option>)}</select></label>;
  if (field.data_type === "boolean") return <label className="rel-wb__checkbox"><input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} /><span>{field.label}</span></label>;
  const inputType = field.data_type === "date" ? "date" : field.data_type === "datetime" ? "datetime-local" : field.data_type === "integer" || field.data_type === "decimal" ? "number" : "text";
  const step = field.data_type === "integer" ? "1" : field.data_type === "decimal" ? "any" : undefined;
  return <label>{label}<input type={inputType} step={step} min={field.data_type === "integer" || field.data_type === "decimal" ? 0 : undefined} required={field.required} value={field.data_type === "datetime" ? datetimeValue(value) : String(value || "")} onChange={(event) => onChange(event.target.value)} /></label>;
}

function Metric({ label, value }: { label: string; value: string }): React.ReactElement {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
