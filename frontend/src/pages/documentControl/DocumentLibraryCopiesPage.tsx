import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  BookOpen,
  CheckCircle2,
  Copy,
  Download,
  MapPin,
  QrCode,
  RefreshCw,
  RotateCcw,
  Search,
  UserRoundCheck,
  X,
} from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  circulatePhysicalCopy,
  downloadPhysicalCopyLabel,
  listIntegratedLibrary,
  listPhysicalCopies,
  registerPhysicalCopy,
  scanPhysicalCopy,
  type ControlledCopyScan,
  type IntegratedLibraryItem,
  type PhysicalCopyRegisterResponse,
} from "../../services/documentLibrary";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentLibrary.css";

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusKind(status: string, overdue = false): "success" | "warning" | "danger" | "neutral" {
  if (overdue || ["RECALLED", "DESTROYED", "WITHDRAWN"].includes(status)) return "danger";
  if (status === "RETURNED") return "success";
  if (status === "ISSUED") return "warning";
  return "neutral";
}

export default function DocumentLibraryCopiesPage() {
  const navigate = useNavigate();
  const { tenant } = useDocumentControlRoute();
  const [params, setParams] = useSearchParams();
  const scanId = params.get("scan") || "";
  const [data, setData] = useState<PhysicalCopyRegisterResponse | null>(null);
  const [documents, setDocuments] = useState<IntegratedLibraryItem[]>([]);
  const [scan, setScan] = useState<ControlledCopyScan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [registerOpen, setRegisterOpen] = useState(false);
  const [page, setPage] = useState(1);
  const query = params.get("q") || "";
  const custody = params.get("custody") || "";
  const overdue = params.get("overdue") === "true";

  const loadRegister = useCallback(async () => {
    if (!tenant || scanId) return;
    setLoading(true);
    setError("");
    try {
      const [copies, library] = await Promise.all([
        listPhysicalCopies(tenant, { q: query || undefined, custody: custody || undefined, overdue, page, perPage: 75 }),
        listIntegratedLibrary(tenant, { status: "ACTIVE", page: 1, perPage: 100 }),
      ]);
      setData(copies);
      setDocuments(library.items.filter((item) => Boolean(item.current_published_revision_id || item.read_target.revision_id)));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The physical document register could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [custody, overdue, page, query, scanId, tenant]);

  const loadScan = useCallback(async () => {
    if (!tenant || !scanId) return;
    setLoading(true);
    setError("");
    try {
      setScan(await scanPhysicalCopy(tenant, scanId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "This physical controlled-copy QR could not be resolved.");
      setScan(null);
    } finally {
      setLoading(false);
    }
  }, [scanId, tenant]);

  useEffect(() => {
    if (scanId) void loadScan();
    else void loadRegister();
  }, [loadRegister, loadScan, scanId]);

  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("scan");
    setParams(next);
    setPage(1);
  };

  if (scanId) {
    return <DocumentControlShell
      title="Physical document scan"
      eyebrow="CONTROLLED COPY"
      subtitle="The QR identifies the physical copy. Portal authentication and document permissions still govern access and custody actions."
      canControl={Boolean(scan?.capabilities.control)}
      actions={<button type="button" className="dc-button" onClick={() => { const next = new URLSearchParams(params); next.delete("scan"); setParams(next); }}><RotateCcw size={14} /> Physical library</button>}
    >
      {loading ? <DocumentControlLoading label="Resolving controlled copy…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void loadScan()} /> : null}
      {scan ? <PhysicalCopyScanPanel tenant={tenant} value={scan} onChange={setScan} onRead={() => navigate(scan.reader_path)} /> : null}
    </DocumentControlShell>;
  }

  return <DocumentControlShell
    title="Physical document library"
    eyebrow="COPY CUSTODY"
    subtitle="Trace every numbered hard copy from its controlled shelf to its custodian, due date, return, recall and final disposition."
    canControl
    actions={<>
      <button type="button" className="dc-button" onClick={() => void loadRegister()}><RefreshCw size={14} /> Refresh</button>
      <button type="button" className="dc-button dc-button--primary" onClick={() => setRegisterOpen(true)}><Copy size={14} /> Register copy</button>
    </>}
  >
    <section className="physical-library" data-testid="physical-document-library">
      <div className="physical-library__metrics">
        <div><strong>{data?.summary.on_shelf || 0}</strong><span>on shelf on this page</span></div>
        <div><strong>{data?.summary.checked_out || 0}</strong><span>with custodians on this page</span></div>
        <div className={(data?.summary.overdue || 0) ? "is-danger" : ""}><strong>{data?.summary.overdue || 0}</strong><span>overdue on this page</span></div>
      </div>
      <div className="physical-library__toolbar">
        <label className="dlibrary__search"><Search size={15} /><input value={query} onChange={(event) => updateFilter("q", event.target.value)} placeholder="Copy number, document, shelf or location" /></label>
        <select value={custody} onChange={(event) => updateFilter("custody", event.target.value)} aria-label="Physical custody filter"><option value="">All custody states</option><option value="ON_SHELF">On shelf</option><option value="CHECKED_OUT">Checked out</option><option value="RECALLED">Recalled</option></select>
        <label className="dgov-check"><input type="checkbox" checked={overdue} onChange={(event) => updateFilter("overdue", event.target.checked ? "true" : "")} /> Overdue only</label>
      </div>

      {loading ? <DocumentControlLoading label="Loading physical copy register…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void loadRegister()} /> : null}
      {!loading && !error && !data?.items.length ? <DocumentControlEmpty icon={Copy} title="No physical controlled copy matches" message="Register a shelf copy or change the custody filters." /> : null}
      {!loading && data?.items.length ? <div className="physical-library__table-wrap"><table className="dc-table physical-library__table"><thead><tr><th>Copy</th><th>Document</th><th>Issue</th><th>Physical location</th><th>Custodian</th><th>Due / state</th><th>Actions</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id} className={item.overdue ? "is-overdue" : ""}>
        <td><strong>{item.copy_number}</strong><small>{item.format}</small></td>
        <td><strong>{item.document.code}</strong><span>{item.document.title}</span></td>
        <td><strong>{item.revision.issue_number ? `Issue ${item.revision.issue_number} · ` : ""}Rev {item.revision.revision_number}</strong><small>{item.revision.status}</small></td>
        <td><strong>{item.location_text || item.home_location_text}</strong><small>Home: {item.home_location_text}</small></td>
        <td><strong>{item.holder_display || "Document Control shelf"}</strong><small>{item.holder_user_id ? "Checked out" : "Available"}</small></td>
        <td><DocumentControlStatus status={item.overdue ? "OVERDUE" : item.status} kind={statusKind(item.status, item.overdue)} /><small>{item.due_back_at ? `Due ${formatDate(item.due_back_at)}` : "No return due"}</small></td>
        <td><div className="physical-library__actions"><button type="button" className="dc-button" onClick={() => { const next = new URLSearchParams(params); next.set("scan", item.id); setParams(next); }}><QrCode size={14} /> Open / scan</button><button type="button" className="dc-button" onClick={() => void downloadPhysicalCopyLabel(tenant, item.id, `${item.document.code}-${item.copy_number}-QR.pdf`)}><Download size={14} /> QR label</button></div></td>
      </tr>)}</tbody></table></div> : null}
      {data && data.pagination.total > data.pagination.per_page ? <footer className="physical-library__pagination"><span>{data.pagination.total} copies</span><button type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><span>Page {page}</span><button type="button" disabled={page * data.pagination.per_page >= data.pagination.total} onClick={() => setPage((value) => value + 1)}>Next</button></footer> : null}
    </section>

    {registerOpen ? <RegisterCopyDialog tenant={tenant} documents={documents} onClose={() => setRegisterOpen(false)} onCreated={() => { setRegisterOpen(false); void loadRegister(); }} /> : null}
  </DocumentControlShell>;
}

function RegisterCopyDialog({ tenant, documents, onClose, onCreated }: { tenant: string; documents: IntegratedLibraryItem[]; onClose: () => void; onCreated: () => void }) {
  const [manualId, setManualId] = useState(documents[0]?.id || "");
  const [copyNumber, setCopyNumber] = useState("");
  const [location, setLocation] = useState("");
  const [format, setFormat] = useState<"HARDCOPY" | "OFFLINE_MEDIA">("HARDCOPY");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selected = useMemo(() => documents.find((item) => item.id === manualId), [documents, manualId]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const revisionId = selected?.current_published_revision_id || selected?.read_target.revision_id;
    if (!manualId || !revisionId) return;
    setBusy(true); setError("");
    try {
      await registerPhysicalCopy(tenant, { manual_id: manualId, revision_id: revisionId, copy_number: copyNumber.trim(), format, location_text: location.trim() });
      onCreated();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The physical copy could not be registered.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="physical-copy-dialog" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><section className="physical-copy-dialog__card" role="dialog" aria-modal="true" aria-label="Register physical controlled copy"><div className="physical-copy-dialog__head"><div><h2>Register physical copy</h2><p>Register the copy at its home shelf first. A QR scan handles later check-out and return custody.</p></div><button type="button" className="dc-button" onClick={onClose}><X size={16} /></button></div><form className="physical-copy-form" onSubmit={submit}>
    <label className="wide"><span>Controlled document</span><select value={manualId} onChange={(event) => setManualId(event.target.value)} required><option value="">Choose document</option>{documents.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.title}</option>)}</select></label>
    <label><span>Copy number</span><input value={copyNumber} onChange={(event) => setCopyNumber(event.target.value)} placeholder="e.g. C01" required /></label>
    <label><span>Format</span><select value={format} onChange={(event) => setFormat(event.target.value as "HARDCOPY" | "OFFLINE_MEDIA")}><option value="HARDCOPY">Hard copy</option><option value="OFFLINE_MEDIA">Offline media</option></select></label>
    <label className="wide"><span>Home shelf / controlled location</span><input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Quality Library · Cabinet Q1 · Shelf 2" required /></label>
    {selected ? <div className="wide"><small>Will register against {selected.code} · {selected.latest_revision?.issue_number ? `Issue ${selected.latest_revision.issue_number} · ` : ""}Rev {selected.latest_revision?.revision_number || selected.read_target.label}</small></div> : null}
    {error ? <div className="dc-form__error wide">{error}</div> : null}
    <div className="physical-copy-form__actions"><button type="button" className="dc-button" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy || !selected || copyNumber.trim().length < 1 || location.trim().length < 2}>{busy ? "Registering…" : "Register on shelf"}</button></div>
  </form></section></div>;
}

function PhysicalCopyScanPanel({ tenant, value, onChange, onRead }: { tenant: string; value: ControlledCopyScan; onChange: (value: ControlledCopyScan) => void; onRead: () => void }) {
  const [due, setDue] = useState("");
  const [location, setLocation] = useState(value.copy.location_text || value.copy.home_location_text);
  const [acknowledged, setAcknowledged] = useState(false);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const checkedOut = ["ISSUED", "RECALLED"].includes(value.copy.status) && Boolean(value.copy.holder_user_id);

  const act = async (action: "CHECK_OUT" | "CHECK_IN" | "VERIFY_LOCATION") => {
    setBusy(true); setError("");
    try {
      const next = await circulatePhysicalCopy(tenant, value.copy.id, {
        action,
        due_back_at: action === "CHECK_OUT" && due ? new Date(due).toISOString() : undefined,
        location_text: action === "VERIFY_LOCATION" || action === "CHECK_IN" ? location.trim() || undefined : undefined,
        acknowledgement: action === "CHECK_OUT" ? acknowledged : undefined,
        comments: comments.trim() || undefined,
      });
      onChange(next);
      setAcknowledged(false);
      setComments("");
      setLocation(next.copy.location_text || next.copy.home_location_text);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The custody action could not be recorded.");
    } finally {
      setBusy(false);
    }
  };

  return <section className="physical-copy-dialog__card physical-copy-scan" data-testid="physical-copy-scan">
    <div className="physical-copy-dialog__head"><div><h2>{value.document.code} · Copy {value.copy.copy_number}</h2><p>{value.document.title}</p></div><DocumentControlStatus status={value.copy.overdue ? "OVERDUE" : value.copy.status} kind={statusKind(value.copy.status, value.copy.overdue)} /></div>
    <div className="physical-copy-dialog__facts">
      <div><span>Controlled issue</span><strong>{value.revision.issue_number ? `Issue ${value.revision.issue_number} · ` : ""}Rev {value.revision.revision_number}</strong></div>
      <div><span>Current physical location</span><strong>{value.copy.location_text || value.copy.home_location_text}</strong></div>
      <div><span>Custodian</span><strong>{value.copy.holder_display || (value.copy.holder_user_id ? "Another authorized user" : "Document Control shelf")}</strong></div>
      <div><span>Return due</span><strong>{formatDate(value.copy.due_back_at)}</strong></div>
      <div><span>Home shelf</span><strong>{value.copy.home_location_text}</strong></div>
      <div><span>Format</span><strong>{value.copy.format}</strong></div>
    </div>

    <div className="physical-library__actions"><button type="button" className="dc-button" onClick={onRead}><BookOpen size={14} /> Read controlled document</button>{value.capabilities.print_label ? <button type="button" className="dc-button" onClick={() => void downloadPhysicalCopyLabel(tenant, value.copy.id, `${value.document.code}-${value.copy.copy_number}-QR.pdf`)}><QrCode size={14} /> Print QR label</button> : null}</div>

    <div className="physical-copy-dialog__form">
      {value.capabilities.check_out && !checkedOut ? <><label><span>Return due</span><input type="datetime-local" value={due} onChange={(event) => setDue(event.target.value)} /></label><label><span>Custody note</span><input value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Optional purpose or location" /></label><label className="wide"><span><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /> I accept custody of this numbered controlled copy and will return it by the due time.</span></label><div className="physical-copy-dialog__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy || !due || !acknowledged} onClick={() => void act("CHECK_OUT")}><UserRoundCheck size={14} /> Check out to me</button></div></> : null}
      {checkedOut && value.capabilities.check_in ? <><label className="wide"><span>Return to shelf / location</span><input value={location} onChange={(event) => setLocation(event.target.value)} /></label><label className="wide"><span>Return note</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} /></label><div className="physical-copy-dialog__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy || location.trim().length < 2} onClick={() => void act("CHECK_IN")}><CheckCircle2 size={14} /> Sign in / return</button></div></> : null}
      {value.capabilities.verify_location ? <><label className="wide"><span>Verify current physical location</span><input value={location} onChange={(event) => setLocation(event.target.value)} /></label><div className="physical-copy-dialog__actions"><button type="button" className="dc-button" disabled={busy || location.trim().length < 2} onClick={() => void act("VERIFY_LOCATION")}><MapPin size={14} /> Verify location</button></div></> : null}
      {error ? <div className="dc-form__error wide">{error}</div> : null}
    </div>

    {value.events.length ? <div className="physical-copy-dialog__history"><h3>Custody history</h3><ol>{value.events.map((event) => <li key={event.id}><strong>{event.event_type.replaceAll("_", " ")}</strong> · {formatDate(event.created_at)}{event.to_location ? ` · ${event.to_location}` : ""}{event.reason ? <small>{event.reason}</small> : null}</li>)}</ol></div> : null}
  </section>;
}
