import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Archive,
  Download,
  FileArchive,
  FilePlus2,
  LockKeyhole,
  BookOpen,
  Search,
  ShieldAlert,
  UnlockKeyhole,
} from "lucide-react";

import { useSearchParams } from "react-router-dom";

import { getCachedUser } from "../../services/auth";
import {
  createRecordSeries,
  getRecord,
  disposeRecord,
  downloadRecord,
  listRecords,
  listRecordSeries,
  prefetchRecord,
  readRecord,
  reindexRecord,
  setRecordLegalHold,
  uploadRecord,
  type RecordSeries,
  type RetainedRecord,
  type RecordRead,
} from "../../services/documentRecordsVault";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentRecordsVault.css";

const RecordPdfPreview = lazy(() => import("./RecordPdfPreview"));

function canControlRecords(): boolean {
  const user = getCachedUser();
  return Boolean(user?.is_amo_admin || user?.role === "AMO_ADMIN" || user?.role === "DOCUMENT_CONTROL_OFFICER");
}

function humanBytes(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function when(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

export default function DocumentRecordsVaultPage() {
  const { tenant } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const requestedRecordId = params.get("record") || "";
  const canControl = canControlRecords();
  const [series, setSeries] = useState<RecordSeries[]>([]);
  const [records, setRecords] = useState<RetainedRecord[]>([]);
  const [focusedRecord, setFocusedRecord] = useState<RetainedRecord | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [seriesId, setSeriesId] = useState("");
  const [sourceModule, setSourceModule] = useState("");
  const [disposition, setDisposition] = useState("");
  const [retentionDue, setRetentionDue] = useState(false);
  const [legalHoldOnly, setLegalHoldOnly] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reading, setReading] = useState<RecordRead | null>(null);
  const [readingId, setReadingId] = useState("");

  const refresh = useCallback(async () => {
    if (!tenant) return;
    setBusy(true);
    setError("");
    try {
      const [seriesResult, recordResult] = await Promise.all([
        listRecordSeries(tenant),
        listRecords(tenant, {
          q: q.trim() || undefined,
          seriesId: seriesId || undefined,
          sourceModule: sourceModule.trim() || undefined,
          dispositionStatus: disposition || undefined,
          retentionDue,
          legalHold: legalHoldOnly ? true : undefined,
          perPage: 100,
        }),
      ]);
      setSeries(seriesResult.items);
      setRecords(recordResult.items);
      setTotal(recordResult.pagination.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Records vault could not be loaded.");
    } finally {
      setBusy(false);
    }
  }, [disposition, legalHoldOnly, q, retentionDue, seriesId, sourceModule, tenant]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!tenant || !requestedRecordId) { setFocusedRecord(null); return; }
    let active = true;
    void getRecord(tenant, requestedRecordId)
      .then((row) => {
        if (!active) return;
        setFocusedRecord(row);
        setReadingId(row.id);
        void readRecord(tenant, row.id).then((content) => { if (active) setReading(content); })
          .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Record reader could not be opened."); });
      })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "The requested retained record could not be opened."); });
    return () => { active = false; };
  }, [requestedRecordId, tenant]);

  const sourceModules = useMemo(
    () => Array.from(new Set(records.map((row) => row.source_module).filter(Boolean) as string[])).sort(),
    [records],
  );
  const openRecord = async (record: RetainedRecord) => {
    setReadingId(record.id); setReading(null); setError("");
    try { setReading(await readRecord(tenant, record.id)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Record preview could not be opened."); }
  };

  if (!tenant) return <DocumentControlError message="Tenant context is unavailable." />;

  return (
    <DocumentControlShell
      title="Records vault"
      subtitle="The tenant warehouse for retained evidence, source records, legal holds and retention-controlled files."
      canControl={canControl}
      actions={<button type="button" className="dc-button" onClick={() => void refresh()}>Refresh</button>}
    >
      <div className="records-vault">
        <section className="records-vault__summary">
          <div><strong>{total}</strong><span>visible retained records</span></div>
          <div><strong>{series.length}</strong><span>accessible record series</span></div>
          {canControl ? <><div><strong>{records.filter((row) => row.legal_hold).length}</strong><span>legal / administrative holds</span></div>
          <div><strong>{records.filter((row) => row.retention_due_at && new Date(row.retention_due_at) <= new Date() && row.disposition_status === "ACTIVE").length}</strong><span>retention actions due</span></div></> : null}
        </section>

        <section className="records-vault__filters" aria-label="Records search and filters">
          <label className="records-vault__search"><Search size={16} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search record number, title, filename, source or indexed metadata" /></label>
          <select value={seriesId} onChange={(event) => setSeriesId(event.target.value)} aria-label="Record series">
            <option value="">All accessible series</option>
            {series.map((row) => <option key={row.id} value={row.id}>{row.code} · {row.title}</option>)}
          </select>
          <select value={sourceModule} onChange={(event) => setSourceModule(event.target.value)} aria-label="Source module">
            <option value="">All source modules</option>
            {sourceModules.map((value) => <option key={value}>{value}</option>)}
          </select>
          <select value={disposition} onChange={(event) => setDisposition(event.target.value)} aria-label="Disposition status">
            <option value="">All statuses</option>
            <option>ACTIVE</option><option>ARCHIVED</option><option>TRANSFERRED</option><option>DISPOSED</option>
          </select>
          {canControl ? <><label><input type="checkbox" checked={retentionDue} onChange={(event) => setRetentionDue(event.target.checked)} /> Retention due</label>
          <label><input type="checkbox" checked={legalHoldOnly} onChange={(event) => setLegalHoldOnly(event.target.checked)} /> Legal hold</label></> : null}
          <button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void refresh()}>Search</button>
        </section>

        {canControl ? <RecordsControlDesk tenant={tenant} series={series} onChanged={() => void refresh()} setNotice={setNotice} setError={setError} /> : null}

        {notice ? <div className="records-vault__notice" role="status">{notice}</div> : null}
        {error ? <DocumentControlError message={error} /> : null}
        {busy && !records.length ? <DocumentControlLoading label="Loading records vault…" /> : null}

        {!busy && !records.length ? <DocumentControlEmpty title="No records match" message="Change the filters or deposit a retained record into an accessible series." /> : null}

        {readingId ? <section className="records-vault__reader" aria-label="Retained record reader">
          <header><h2>Record reader</h2><button type="button" className="dc-button" onClick={() => { setReadingId(""); setReading(null); }}>Close</button></header>
          {reading ? <>
            <p>{reading.filename} · {reading.metadata.text_index?.engine || "Index pending"}</p>
            {reading.metadata.text_index?.warning ? <p role="status">{reading.metadata.text_index.warning}</p> : null}
            {reading.mime_type === "application/pdf" ? <Suspense fallback={<DocumentControlLoading label="Loading PDF reader…" />}><RecordPdfPreview tenant={tenant} recordId={reading.record_id} /></Suspense> : null}
            {reading.metadata.extracted && Object.keys(reading.metadata.extracted).length ? <dl className="records-vault__metadata">{Object.entries(reading.metadata.extracted).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl> : null}
            <pre>{reading.text || "The text index is pending or this file has no searchable text. Download the original to view it."}</pre>
            {reading.truncated ? <small>Preview limited to 120,000 characters. Download the original for the complete record.</small> : null}
          </> : <DocumentControlLoading label="Opening record…" />}
        </section> : null}

        {focusedRecord ? <div className="records-vault__focused">
          <span><strong>Opened from search</strong><small>{focusedRecord.series_code} · {focusedRecord.record_number}</small></span>
          <button type="button" className="dc-button" onClick={() => { const next = new URLSearchParams(params); next.delete("record"); setParams(next, { replace: true }); }}>Clear</button>
        </div> : null}
        <div className="records-vault__table-wrap">
          <table className="records-vault__table">
            <thead><tr><th scope="col">Record</th><th scope="col">Source</th><th scope="col">File / index</th><th scope="col">Retention</th><th scope="col">Actions</th></tr></thead>
            <tbody>{[...(focusedRecord ? [focusedRecord] : []), ...records.filter((record) => record.id !== focusedRecord?.id)].map((record) => (
              <tr key={record.id}>
                <td data-label="Record"><strong>{record.title}</strong><small>{record.series_code} · {record.record_number}</small>
                  <DocumentControlStatus kind={record.legal_hold ? "danger" : record.disposition_status === "ACTIVE" ? "success" : "neutral"}>{record.legal_hold ? "LEGAL HOLD" : record.disposition_status}</DocumentControlStatus>
                </td>
                <td data-label="Source">{record.source_module || "—"}<small>{record.source_entity_type || ""}</small></td>
                <td data-label="File / index">{record.filename || "Restricted"}<small>{humanBytes(record.size_bytes)} · {record.metadata?.text_index?.status || "—"}</small>
                  {record.metadata?.extracted?.page_count ? <small>{record.metadata.extracted.page_count} pages</small> : null}
                </td>
                <td data-label="Retention">Captured {when(record.captured_at)}<small>Due {when(record.retention_due_at)}</small></td>
                <td data-label="Actions"><div className="records-vault__actions">
                  {record.content_access ? <button type="button" className="dc-button" onMouseEnter={() => prefetchRecord(tenant, record.id)} onFocus={() => prefetchRecord(tenant, record.id)} onClick={() => void openRecord(record)}><BookOpen size={14} /> Read</button> : null}
                  {record.content_access && record.download_url ? <button type="button" className="dc-button" onClick={() => void downloadRecord(tenant, record).catch((caught) => setError(caught instanceof Error ? caught.message : "Download failed."))}><Download size={14} /> Download</button> : null}
                  {canControl && record.metadata?.text_index?.status !== "READY" ? <button type="button" className="dc-button" onClick={() => void reindexRecord(tenant, record.id).then(() => { setNotice("Indexing queued."); void refresh(); }).catch((caught) => setError(caught instanceof Error ? caught.message : "Indexing failed."))}>Retry index</button> : null}
                  {canControl ? <RecordControlButtons tenant={tenant} record={record} onChanged={() => void refresh()} setNotice={setNotice} setError={setError} /> : null}
                </div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </DocumentControlShell>
  );
}

function RecordsControlDesk({
  tenant,
  series,
  onChanged,
  setNotice,
  setError,
}: {
  tenant: string;
  series: RecordSeries[];
  onChanged: () => void;
  setNotice: (value: string) => void;
  setError: (value: string) => void;
}) {
  const [showSeries, setShowSeries] = useState(false);
  const [showDeposit, setShowDeposit] = useState(false);
  const [busy, setBusy] = useState(false);

  const [seriesCode, setSeriesCode] = useState("");
  const [seriesTitle, setSeriesTitle] = useState("");
  const [ownerDepartment, setOwnerDepartment] = useState("");
  const [retentionYears, setRetentionYears] = useState(7);

  const [depositSeries, setDepositSeries] = useState("");
  const [recordNumber, setRecordNumber] = useState("");
  const [title, setTitle] = useState("");
  const [sourceModule, setSourceModule] = useState("DOCUMENT_CONTROL");
  const [sourceEntityType, setSourceEntityType] = useState("");
  const [sourceEntityId, setSourceEntityId] = useState("");
  const [capturedAt, setCapturedAt] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [controller, setController] = useState<AbortController | null>(null);
  const [artifact, setArtifact] = useState<File | null>(null);

  const run = async (operation: () => Promise<unknown>, message: string) => {
    setBusy(true); setError("");
    try { await operation(); setNotice(message); onChanged(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Records operation failed."); }
    finally { setBusy(false); }
  };

  const addSeries = (event: FormEvent) => {
    event.preventDefault();
    void run(() => createRecordSeries(tenant, {
      code: seriesCode,
      title: seriesTitle,
      owner_department: ownerDepartment,
      retention_years: retentionYears,
      disposition_method: "REVIEW_AT_EXPIRY",
      restricted: true,
      controllers_can_read: true,
    }), "Record series created.");
  };

  const deposit = (event: FormEvent) => {
    event.preventDefault();
    if (!artifact) { setError("Choose a file to deposit."); return; }
    const abort = new AbortController();
    setController(abort); setProgress(0);
    void run(() => uploadRecord(tenant, {
      artifact,
      seriesId: depositSeries,
      recordNumber,
      title,
      sourceModule,
      sourceEntityType,
      sourceEntityId,
      capturedAt,
      metadata: { description, tags },
    }, { signal: abort.signal, onProgress: setProgress }), "Record deposited. Text and metadata indexing is queued.")
      .finally(() => { setController(null); setProgress(null); });
  };

  return <section className="records-vault__control">
    <header><div><FileArchive size={18} /><span><strong>Records control desk</strong><small>Deposit evidence into a governed series; do not use the publication workflow for retained records.</small></span></div>
      <div><button type="button" className="dc-button" onClick={() => setShowSeries((value) => !value)}>New series</button><button type="button" className="dc-button dc-button--primary" onClick={() => setShowDeposit((value) => !value)}><FilePlus2 size={14} /> Deposit record</button></div>
    </header>
    {showSeries ? <form onSubmit={addSeries} className="records-vault__form">
      <label><span>Series code</span><input value={seriesCode} onChange={(e) => setSeriesCode(e.target.value)} required /></label>
      <label><span>Series title</span><input value={seriesTitle} onChange={(e) => setSeriesTitle(e.target.value)} required /></label>
      <label><span>Owner department</span><input value={ownerDepartment} onChange={(e) => setOwnerDepartment(e.target.value)} required /></label>
      <label><span>Retention years</span><input type="number" min={1} max={100} value={retentionYears} onChange={(e) => setRetentionYears(Number(e.target.value))} required /></label>
      <button className="dc-button" disabled={busy}>Create series</button>
    </form> : null}
    {showDeposit ? <form onSubmit={deposit} className="records-vault__form">
      <label><span>Record series</span><select value={depositSeries} onChange={(e) => setDepositSeries(e.target.value)} required><option value="">Select series</option>{series.map((row) => <option key={row.id} value={row.id}>{row.code} · {row.title}</option>)}</select></label>
      <label><span>Record number</span><input value={recordNumber} onChange={(e) => setRecordNumber(e.target.value)} required /></label>
      <label><span>Title</span><input value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
      <label><span>Source module</span><input value={sourceModule} onChange={(e) => setSourceModule(e.target.value)} required /></label>
      <label><span>Source entity type</span><input value={sourceEntityType} onChange={(e) => setSourceEntityType(e.target.value)} maxLength={80} placeholder="e.g. AUDIT_FINDING" /></label>
      <label><span>Source entity ID</span><input value={sourceEntityId} onChange={(e) => setSourceEntityId(e.target.value)} maxLength={128} /></label>
      <label><span>Captured at</span><input type="datetime-local" value={capturedAt} onChange={(e) => setCapturedAt(e.target.value)} /></label>
      <label><span>Tags</span><input value={tags} onChange={(e) => setTags(e.target.value)} maxLength={500} placeholder="Comma separated" /></label>
      <label className="wide"><span>Description</span><input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} /></label>
      <label className="wide"><span>Evidence file</span><input type="file" onChange={(e) => setArtifact(e.target.files?.[0] || null)} required /></label>
      {progress !== null ? <div className="records-vault__progress" role="status"><progress value={progress} max={100} /> {progress}% uploaded {controller ? <button type="button" className="dc-button" onClick={() => controller.abort()}>Cancel</button> : null}</div> : null}
      <button className="dc-button dc-button--primary" disabled={busy || !artifact}>Deposit</button>
    </form> : null}
  </section>;
}

function RecordControlButtons({
  tenant,
  record,
  onChanged,
  setNotice,
  setError,
}: {
  tenant: string;
  record: RetainedRecord;
  onChanged: () => void;
  setNotice: (value: string) => void;
  setError: (value: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const reason = (action: string) => window.prompt(`Reason for ${action}:`)?.trim() || "";

  const hold = async (enabled: boolean) => {
    const why = reason(enabled ? "placing this record on hold" : "releasing this record hold");
    if (!why) return;
    setBusy(true);
    try { await setRecordLegalHold(tenant, record.id, enabled, why); setNotice(enabled ? "Legal / administrative hold applied." : "Hold released."); onChanged(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Hold update failed."); }
    finally { setBusy(false); }
  };

  const disposition = async (status: "ARCHIVED" | "TRANSFERRED" | "DISPOSED") => {
    const why = reason(`recording ${status.toLowerCase()} disposition`);
    if (!why) return;
    setBusy(true);
    try { await disposeRecord(tenant, record.id, status, why); setNotice(`Disposition recorded as ${status}.`); onChanged(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Disposition failed."); }
    finally { setBusy(false); }
  };

  return <>
    <button type="button" className="dc-button" disabled={busy} onClick={() => void hold(!record.legal_hold)}>{record.legal_hold ? <UnlockKeyhole size={14} /> : <LockKeyhole size={14} />}{record.legal_hold ? "Release hold" : "Legal hold"}</button>
    {!record.legal_hold && record.disposition_status === "ACTIVE" ? <>
      <button type="button" className="dc-button" disabled={busy} onClick={() => void disposition("ARCHIVED")}><Archive size={14} /> Archive</button>
      <button type="button" className="dc-button" disabled={busy} onClick={() => void disposition("TRANSFERRED")}>Transfer</button>
      <button type="button" className="dc-button dc-button--danger" disabled={busy} onClick={() => void disposition("DISPOSED")}><ShieldAlert size={14} /> Record disposition</button>
    </> : null}
  </>;
}
