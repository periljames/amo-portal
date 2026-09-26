import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Archive,
  Download,
  FileArchive,
  FilePlus2,
  LockKeyhole,
  Search,
  ShieldAlert,
  UnlockKeyhole,
} from "lucide-react";

import { getCachedUser } from "../../services/auth";
import {
  createRecordSeries,
  disposeRecord,
  downloadRecord,
  listRecords,
  listRecordSeries,
  setRecordLegalHold,
  uploadRecord,
  type RecordSeries,
  type RetainedRecord,
} from "../../services/documentRecordsVault";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentRecordsVault.css";

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
  const canControl = canControlRecords();
  const [series, setSeries] = useState<RecordSeries[]>([]);
  const [records, setRecords] = useState<RetainedRecord[]>([]);
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

  const sourceModules = useMemo(
    () => Array.from(new Set(records.map((row) => row.source_module).filter(Boolean) as string[])).sort(),
    [records],
  );

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
          <div><strong>{records.filter((row) => row.legal_hold).length}</strong><span>legal / administrative holds</span></div>
          <div><strong>{records.filter((row) => row.retention_due_at && new Date(row.retention_due_at) <= new Date() && row.disposition_status === "ACTIVE").length}</strong><span>retention actions due</span></div>
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
          <label><input type="checkbox" checked={retentionDue} onChange={(event) => setRetentionDue(event.target.checked)} /> Retention due</label>
          <label><input type="checkbox" checked={legalHoldOnly} onChange={(event) => setLegalHoldOnly(event.target.checked)} /> Legal hold</label>
          <button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void refresh()}>Search</button>
        </section>

        {canControl ? <RecordsControlDesk tenant={tenant} series={series} onChanged={() => void refresh()} setNotice={setNotice} setError={setError} /> : null}

        {notice ? <div className="records-vault__notice" role="status">{notice}</div> : null}
        {error ? <DocumentControlError message={error} /> : null}
        {busy && !records.length ? <DocumentControlLoading label="Loading records vault…" /> : null}

        {!busy && !records.length ? <DocumentControlEmpty title="No records match" message="Change the filters or deposit a retained record into an accessible series." /> : null}

        <div className="records-vault__list">
          {records.map((record) => (
            <article key={record.id} className="records-vault__record">
              <header>
                <div><small>{record.series_code} · {record.record_number}</small><h2>{record.title}</h2></div>
                <div className="records-vault__status">
                  <DocumentControlStatus kind={record.legal_hold ? "danger" : record.disposition_status === "ACTIVE" ? "success" : "neutral"}>
                    {record.legal_hold ? "LEGAL HOLD" : record.disposition_status}
                  </DocumentControlStatus>
                </div>
              </header>
              <dl>
                <div><dt>Source</dt><dd>{record.source_module || "—"}{record.source_entity_type ? ` · ${record.source_entity_type}` : ""}</dd></div>
                <div><dt>Captured</dt><dd>{when(record.captured_at)}</dd></div>
                <div><dt>Retention due</dt><dd>{when(record.retention_due_at)}</dd></div>
                <div><dt>File</dt><dd>{record.filename || "Restricted"} · {humanBytes(record.size_bytes)}</dd></div>
              </dl>
              <div className="records-vault__actions">
                {record.content_access && record.download_url ? <button type="button" className="dc-button" onClick={() => void downloadRecord(tenant, record).catch((caught) => setError(caught instanceof Error ? caught.message : "Download failed."))}><Download size={14} /> Download</button> : null}
                {canControl ? <RecordControlButtons tenant={tenant} record={record} onChanged={() => void refresh()} setNotice={setNotice} setError={setError} /> : null}
              </div>
            </article>
          ))}
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
    void run(() => uploadRecord(tenant, {
      artifact,
      seriesId: depositSeries,
      recordNumber,
      title,
      sourceModule,
    }), "Record deposited into the tenant vault.");
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
      <label className="wide"><span>Evidence file</span><input type="file" onChange={(e) => setArtifact(e.target.files?.[0] || null)} required /></label>
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
