import { useEffect, useMemo, useState } from "react";
import { BookOpen, FilePlus2, FolderOpen, Search, UploadCloud, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getMasterList,
  listFeaturedManuals,
  listManuals,
  subscribeManualsUpdated,
  type ManualFeaturedEntry,
  type ManualSummary,
} from "../../services/manuals";
import { getCachedUser } from "../../services/auth";
import {
  previewPublicationUpload,
  uploadPublicationRevision,
  type PublicationUploadPreview,
  type PublicationUploadResult,
} from "../../services/publications";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import "./manualsDashboard.css";
import "./publicationsDashboard.css";

type MasterRow = {
  manual_id: string;
  code: string;
  title: string;
  manual_type?: string;
  current_revision: string | null;
  current_status: string;
  current_issue_number?: string | null;
  current_effective_date?: string | null;
  pending_ack_count: number;
  source_type?: string | null;
  source_filename?: string | null;
  page_count?: number | null;
  section_count?: number;
  block_count?: number;
};

type UploadFormState = {
  partNumber: string;
  manualType: string;
  title: string;
  revisionNumber: string;
  issueNumber: string;
  effectiveDate: string;
  ownerRole: string;
  changeLog: string;
};

type QueueStatus = "previewing" | "ready" | "uploading" | "done" | "error";

type UploadQueueItem = {
  id: string;
  file: File;
  status: QueueStatus;
  preview: PublicationUploadPreview | null;
  form: UploadFormState;
  result: PublicationUploadResult | null;
  error: string;
};

const EMPTY_FORM: UploadFormState = {
  partNumber: "",
  manualType: "GENERAL",
  title: "",
  revisionNumber: "00",
  issueNumber: "00",
  effectiveDate: "",
  ownerRole: "Library",
  changeLog: "",
};

export function resolveNextRevisionId(previousRevisionId: string, revisions: Array<{ id: string }>): string {
  if (!revisions.length) return "";
  if (previousRevisionId && revisions.some((row) => row.id === previousRevisionId)) return previousRevisionId;
  return revisions[0].id;
}

function canWritePublications(): boolean {
  const user = getCachedUser();
  const role = String((user as any)?.role || "");
  return Boolean(
    user?.is_superuser ||
    user?.is_amo_admin ||
    ["QUALITY_MANAGER", "QUALITY_INSPECTOR", "DOCUMENT_CONTROL_OFFICER"].includes(role),
  );
}

function fileStem(filename: string): string {
  return filename.replace(/\.(docx|pdf)$/i, "").replace(/[_-]+/g, " ").trim();
}

function fallbackCode(filename: string): string {
  const stem = filename.replace(/\.(docx|pdf)$/i, "").toUpperCase();
  return stem.replace(/[^A-Z0-9]+/g, "/").replace(/^\/+|\/+$/g, "").slice(0, 32);
}

function queueId(file: File, index: number): string {
  return `${file.name}:${file.size}:${file.lastModified}:${index}`;
}

function buildForm(file: File, preview: PublicationUploadPreview | null): UploadFormState {
  const metadata = preview?.metadata || {};
  return {
    partNumber: String(metadata.part_number || fallbackCode(file.name)),
    manualType: String(metadata.manual_type || "GENERAL"),
    title: String(metadata.title || preview?.heading || fileStem(file.name)),
    revisionNumber: String(metadata.revision_number || "00"),
    issueNumber: String(metadata.issue_number || "00"),
    effectiveDate: String(metadata.effective_date || ""),
    ownerRole: "Library",
    changeLog: "",
  };
}

export default function PublicationsDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useManualRouteContext();
  const canWrite = canWritePublications();
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
  const [featured, setFeatured] = useState<ManualFeaturedEntry[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [batchUploading, setBatchUploading] = useState(false);
  const [batchMessage, setBatchMessage] = useState("");

  const refresh = async () => {
    if (!tenant) return;
    setLoading(true);
    const [manualRows, master, featuredRows] = await Promise.all([
      listManuals(tenant).catch(() => []),
      getMasterList(tenant).catch(() => []),
      listFeaturedManuals(tenant).catch(() => []),
    ]);
    setManuals(manualRows);
    setMasterRows(master as MasterRow[]);
    setFeatured(featuredRows);
    setLoading(false);
  };

  useEffect(() => {
    void refresh();
  }, [tenant]);

  useEffect(() => {
    if (!tenant) return;
    return subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenant) void refresh();
    });
  }, [tenant]);

  const manualById = useMemo(() => new Map(manuals.map((manual) => [manual.id, manual])), [manuals]);
  const rows = useMemo(() => {
    const masterById = new Map(masterRows.map((row) => [row.manual_id, row]));
    return manuals.map((manual) => {
      const master = masterById.get(manual.id);
      return {
        ...manual,
        current_revision_label: master?.current_revision || null,
        current_revision_id: manual.current_published_rev_id,
        current_status: master?.current_status || manual.status,
        current_issue_number: master?.current_issue_number || null,
        pending_ack_count: master?.pending_ack_count || 0,
        source_type: master?.source_type || null,
        page_count: master?.page_count || null,
        section_count: master?.section_count || 0,
        block_count: master?.block_count || 0,
      };
    });
  }, [manuals, masterRows]);

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => [row.code, row.title, row.manual_type, row.current_status].some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [query, rows]);

  const updateQueue = (id: string, updater: (item: UploadQueueItem) => UploadQueueItem) => {
    setQueue((current) => current.map((item) => item.id === id ? updater(item) : item));
  };

  const inspectFiles = async (files: FileList | null) => {
    if (!files || !tenant) return;
    const selected = Array.from(files).filter((file) => /\.(docx|pdf)$/i.test(file.name));
    if (!selected.length) {
      setBatchMessage("Choose one or more DOCX or PDF files.");
      return;
    }
    const nextQueue: UploadQueueItem[] = selected.map((file, index) => ({
      id: queueId(file, index),
      file,
      status: "previewing",
      preview: null,
      form: buildForm(file, null),
      result: null,
      error: "",
    }));
    setQueue(nextQueue);
    setBatchMessage("");
    await Promise.all(nextQueue.map(async (item) => {
      try {
        const preview = await previewPublicationUpload(tenant, item.file);
        updateQueue(item.id, (current) => ({ ...current, preview, form: buildForm(item.file, preview), status: "ready", error: "" }));
      } catch (caught) {
        updateQueue(item.id, (current) => ({ ...current, status: "error", error: caught instanceof Error ? caught.message : "Preview failed" }));
      }
    }));
  };

  const updateForm = (id: string, key: keyof UploadFormState, value: string) => {
    updateQueue(id, (item) => ({ ...item, form: { ...item.form, [key]: value } }));
  };

  const removeQueueItem = (id: string) => {
    setQueue((current) => current.filter((item) => item.id !== id));
  };

  const uploadBatch = async () => {
    if (!tenant || batchUploading) return;
    const candidates = queue.filter((item) => item.status === "ready" || item.status === "error");
    if (!candidates.length) return;
    setBatchUploading(true);
    setBatchMessage("");
    const completed: PublicationUploadResult[] = [];
    for (const candidate of candidates) {
      if (!candidate.form.partNumber.trim() || !candidate.form.title.trim() || !candidate.form.revisionNumber.trim()) {
        updateQueue(candidate.id, (item) => ({ ...item, status: "error", error: "Part number, title, and revision are required." }));
        continue;
      }
      updateQueue(candidate.id, (item) => ({ ...item, status: "uploading", error: "" }));
      try {
        const result = await uploadPublicationRevision(tenant, {
          code: candidate.form.partNumber.trim(),
          title: candidate.form.title.trim(),
          rev_number: candidate.form.revisionNumber.trim(),
          issue_number: candidate.form.issueNumber.trim(),
          effective_date: candidate.form.effectiveDate || undefined,
          manual_type: candidate.form.manualType.trim() || "GENERAL",
          owner_role: candidate.form.ownerRole.trim() || "Library",
          change_log: candidate.form.changeLog.trim() || undefined,
          file: candidate.file,
        });
        completed.push(result);
        updateQueue(candidate.id, (item) => ({ ...item, status: "done", result, error: "" }));
      } catch (caught) {
        updateQueue(candidate.id, (item) => ({ ...item, status: "error", error: caught instanceof Error ? caught.message : "Upload failed" }));
      }
    }
    setBatchUploading(false);
    await refresh();
    if (completed.length === 1) {
      const result = completed[0];
      navigate(`${basePath}/${result.manual_id}/rev/${result.revision_id}/read`);
      return;
    }
    setBatchMessage(completed.length ? `${completed.length} publication file(s) uploaded. Review the register before routing revisions for approval.` : "No publication was uploaded.");
  };

  const openPublication = (manualId: string, revisionId?: string | null) => {
    if (revisionId) navigate(`${basePath}/${manualId}/rev/${revisionId}/read`);
    else navigate(`${basePath}/${manualId}`);
  };

  const closeUpload = () => {
    if (batchUploading) return;
    setUploadOpen(false);
    setQueue([]);
    setBatchMessage("");
  };

  return (
    <ManualsPageLayout
      title="Publications"
      subtitle="Controlled manuals, legislation, procedures, forms, and technical publications in one searchable library."
      actions={canWrite ? (
        <button type="button" className="manuals-primary-btn" onClick={() => setUploadOpen(true)}><UploadCloud size={16} /> Upload publications</button>
      ) : undefined}
    >
      <section className="publications-overview-strip" aria-label="Publication summary">
        <div><strong>{rows.length}</strong><span>Controlled titles</span></div>
        <div><strong>{rows.filter((row) => row.current_revision_id).length}</strong><span>Published revisions</span></div>
        <div><strong>{masterRows.reduce((sum, row) => sum + Number(row.pending_ack_count || 0), 0)}</strong><span>Pending acknowledgements</span></div>
        <div><strong>{masterRows.filter((row) => row.source_type === "PDF").length}</strong><span>PDF sources</span></div>
      </section>

      {featured.length ? (
        <section className="publications-featured" aria-label="Frequently used publications">
          <div className="publications-section-heading"><div><h2>Frequently used</h2><p>Open the current controlled revision without searching the register.</p></div></div>
          <div className="publications-featured-grid">
            {featured.map((item) => {
              const manual = manualById.get(item.manual_id);
              return (
                <button type="button" key={item.manual_id} onClick={() => openPublication(item.manual_id, manual?.current_published_rev_id)}>
                  <BookOpen size={18} />
                  <span><strong>{item.code}</strong><small>{item.title}</small></span>
                  <em>{item.open_count} opens</em>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="publications-register">
        <div className="publications-register__toolbar">
          <div><h2>Publication register</h2><p>Only revision IDs returned by the API are used to open the reader; revision labels are never treated as record identifiers.</p></div>
          <label className="publications-register__search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, title, type, or status" /></label>
        </div>
        <div className="publications-table-wrap">
          <table className="publications-table">
            <thead><tr><th>Code</th><th>Publication</th><th>Issue / revision</th><th>Format</th><th>Reader index</th><th>Status</th><th /></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7}>Loading publication register…</td></tr> : null}
              {!loading && filteredRows.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.code}</strong></td>
                  <td><span>{row.title}</span><small>{row.manual_type}</small></td>
                  <td><span>Issue {row.current_issue_number || "—"}</span><small>Rev {row.current_revision_label || "—"}</small></td>
                  <td>{row.source_type || "—"}{row.page_count ? <small>{row.page_count} pages</small> : null}</td>
                  <td><span>{row.section_count} sections</span><small>{row.block_count} text blocks</small></td>
                  <td><span className={`publications-status status-${String(row.current_status || "unknown").toLowerCase()}`}>{String(row.current_status || "Unknown").replaceAll("_", " ")}</span>{row.pending_ack_count ? <small>{row.pending_ack_count} ack pending</small> : null}</td>
                  <td><button type="button" className="publications-open-button" onClick={() => openPublication(row.id, row.current_revision_id)}><FolderOpen size={15} /> {row.current_revision_id ? "Open reader" : "View record"}</button></td>
                </tr>
              ))}
              {!loading && !filteredRows.length ? <tr><td colSpan={7}>No publication matches the current search.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      {uploadOpen ? (
        <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeUpload(); }}>
          <section className="publications-upload-dialog" role="dialog" aria-modal="true" aria-label="Upload publications">
            <header>
              <div><h2>Upload controlled publications</h2><p>Select a DOCX, searchable PDF, image-only PDF, or a batch containing several manual parts. Each file is inspected before upload.</p></div>
              <button type="button" onClick={closeUpload} aria-label="Close upload dialog"><X size={18} /></button>
            </header>
            <div className="publications-file-picker">
              <FilePlus2 size={22} />
              <div><strong>Choose DOCX or PDF files</strong><span>DOCX up to 10 MB · PDF up to 50 MB per file</span></div>
              <input type="file" multiple accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void inspectFiles(event.target.files)} />
            </div>
            <div className="publications-upload-queue">
              {queue.map((item, index) => {
                const likelyImageOnly = item.preview?.source_type === "PDF" && item.preview.paragraph_count === 0 && !item.preview.excerpt.trim();
                return (
                  <article key={item.id} className={`publications-upload-item status-${item.status}`}>
                    <div className="publications-upload-item__head">
                      <div><strong>{index + 1}. {item.file.name}</strong><span>{item.preview?.source_type || item.file.name.split(".").pop()?.toUpperCase()} · {(item.file.size / 1024 / 1024).toFixed(2)} MB · {item.status}</span></div>
                      <button type="button" disabled={batchUploading} onClick={() => removeQueueItem(item.id)} aria-label={`Remove ${item.file.name}`}><X size={15} /></button>
                    </div>
                    {likelyImageOnly ? <p className="publications-image-only-note">No dependable text layer was detected. This file will use the original PDF reader instead of fabricated OCR text.</p> : null}
                    {item.error ? <p className="publications-upload-error">{item.error}</p> : null}
                    <div className="publications-upload-fields">
                      <label><span>Part / publication code</span><input value={item.form.partNumber} onChange={(event) => updateForm(item.id, "partNumber", event.target.value)} /></label>
                      <label><span>Publication type</span><input value={item.form.manualType} onChange={(event) => updateForm(item.id, "manualType", event.target.value)} /></label>
                      <label className="wide"><span>Title</span><input value={item.form.title} onChange={(event) => updateForm(item.id, "title", event.target.value)} /></label>
                      <label><span>Issue</span><input value={item.form.issueNumber} onChange={(event) => updateForm(item.id, "issueNumber", event.target.value)} /></label>
                      <label><span>Revision</span><input value={item.form.revisionNumber} onChange={(event) => updateForm(item.id, "revisionNumber", event.target.value)} /></label>
                      <label><span>Effective date</span><input type="date" value={item.form.effectiveDate} onChange={(event) => updateForm(item.id, "effectiveDate", event.target.value)} /></label>
                      <label><span>Owner</span><input value={item.form.ownerRole} onChange={(event) => updateForm(item.id, "ownerRole", event.target.value)} /></label>
                      <label className="wide"><span>Intake / change note</span><textarea rows={2} value={item.form.changeLog} onChange={(event) => updateForm(item.id, "changeLog", event.target.value)} /></label>
                    </div>
                    {item.preview ? (
                      <details><summary>Detected outline ({item.preview.outline.length})</summary>{item.preview.outline.length ? <ol>{item.preview.outline.slice(0, 30).map((heading, headingIndex) => <li key={`${heading}-${headingIndex}`}>{heading}</li>)}</ol> : <p>No document headings were detected. PDF pages will remain directly accessible.</p>}</details>
                    ) : item.status === "previewing" ? <p>Inspecting metadata and structure…</p> : null}
                  </article>
                );
              })}
              {!queue.length ? <div className="publications-upload-empty">No files selected.</div> : null}
            </div>
            <footer>
              <span>{batchMessage}</span>
              <div><button type="button" onClick={closeUpload} disabled={batchUploading}>Cancel</button><button type="button" className="primary" onClick={() => void uploadBatch()} disabled={batchUploading || !queue.some((item) => item.status === "ready" || item.status === "error")}><UploadCloud size={16} /> {batchUploading ? "Uploading batch…" : `Upload ${queue.length || ""} file${queue.length === 1 ? "" : "s"}`}</button></div>
            </footer>
          </section>
        </div>
      ) : null}
    </ManualsPageLayout>
  );
}
