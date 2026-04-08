import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileSearch, FolderOpen, GitCompareArrows, UploadCloud, Workflow } from "lucide-react";

import {
  getMasterList,
  listFeaturedManuals,
  listManuals,
  previewDocxUpload,
  subscribeManualsUpdated,
  uploadDocxRevision,
  type ManualDocxPreview,
  type ManualFeaturedEntry,
  type ManualSummary,
} from "../../services/manuals";
import { getCachedUser } from "../../services/auth";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import "./manualsDashboard.css";

type MasterRow = {
  manual_id: string;
  code: string;
  title: string;
  current_revision: string | null;
  current_status: string;
  pending_ack_count: number;
};

export function resolveNextRevisionId(previousRevisionId: string, revisions: Array<{ id: string }>): string {
  if (!revisions.length) return "";
  if (previousRevisionId && revisions.some((row) => row.id === previousRevisionId)) return previousRevisionId;
  return revisions[0].id;
}

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

function canWriteManuals() {
  const user = getCachedUser();
  const role = String((user as any)?.role || "");
  return !!user?.is_superuser || !!user?.is_amo_admin || ["QUALITY_MANAGER", "QUALITY_INSPECTOR", "DOCUMENT_CONTROL_OFFICER"].includes(role);
}

function mergeRows(manuals: ManualSummary[], masterRows: MasterRow[]) {
  const byId = new Map(masterRows.map((row) => [row.manual_id, row]));
  return manuals.map((manual) => {
    const meta = byId.get(manual.id);
    return {
      manual_id: manual.id,
      code: manual.code,
      title: manual.title,
      manual_type: manual.manual_type,
      current_revision: meta?.current_revision || null,
      current_status: meta?.current_status || manual.status,
      pending_ack_count: meta?.pending_ack_count || 0,
    };
  });
}

export default function ManualsDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useManualRouteContext();
  const canWrite = canWriteManuals();

  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
  const [featured, setFeatured] = useState<ManualFeaturedEntry[]>([]);
  const [query, setQuery] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState<UploadFormState>(EMPTY_FORM);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ManualDocxPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  const refresh = () => {
    if (!tenant) return;
    listManuals(tenant).then(setManuals).catch(() => setManuals([]));
    getMasterList(tenant).then((rows) => setMasterRows(rows as MasterRow[])).catch(() => setMasterRows([]));
    listFeaturedManuals(tenant).then(setFeatured).catch(() => setFeatured([]));
  };

  useEffect(() => {
    refresh();
  }, [tenant]);

  useEffect(() => {
    if (!tenant) return;
    const unsubscribe = subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenant) refresh();
    });
    return unsubscribe;
  }, [tenant]);

  const rows = useMemo(() => mergeRows(manuals, masterRows), [manuals, masterRows]);
  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) =>
      [row.code, row.title, row.manual_type, row.current_status, row.current_revision || ""]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [rows, query]);

  const nextActions = useMemo(() => {
    return rows
      .filter((row) => row.pending_ack_count > 0 || !row.current_revision || row.current_status !== "PUBLISHED")
      .sort((a, b) => Number(b.pending_ack_count) - Number(a.pending_ack_count))
      .slice(0, 5);
  }, [rows]);

  const kpis = useMemo(
    () => ({
      total: rows.length,
      active: rows.filter((row) => row.current_status === "PUBLISHED").length,
      drafts: rows.filter((row) => row.current_status === "DRAFT").length,
      pendingKcaa: rows.filter((row) => row.current_status === "REGULATOR_SIGNOFF").length,
      pendingAcks: rows.reduce((sum, row) => sum + Number(row.pending_ack_count || 0), 0),
    }),
    [rows],
  );

  const applyPreviewMetadata = (payload: ManualDocxPreview) => {
    const metadata = payload.metadata || {};
    setUploadForm((prev) => ({
      ...prev,
      partNumber: metadata.part_number || prev.partNumber,
      manualType: metadata.manual_type || prev.manualType,
      title: metadata.title || payload.heading || prev.title,
      revisionNumber: metadata.revision_number || prev.revisionNumber,
      issueNumber: metadata.issue_number || prev.issueNumber,
      effectiveDate: metadata.effective_date || prev.effectiveDate,
    }));
  };

  const onPickFile = async (file: File | null) => {
    setSelectedFile(file);
    setPreview(null);
    setErrorMessage("");
    setStatusMessage("");
    if (!tenant || !file) return;
    if (!file.name.toLowerCase().endsWith(".docx")) {
      setErrorMessage("Please select a DOCX file.");
      return;
    }
    setPreviewLoading(true);
    try {
      const payload = await previewDocxUpload(tenant, file);
      setPreview(payload);
      applyPreviewMetadata(payload);
      setStatusMessage("Metadata extracted from the uploaded document.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to preview the uploaded DOCX.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const resetUploadState = () => {
    setUploadOpen(false);
    setSelectedFile(null);
    setPreview(null);
    setUploadForm(EMPTY_FORM);
    setPreviewLoading(false);
    setUploading(false);
    setErrorMessage("");
    setStatusMessage("");
  };

  const onUpload = async () => {
    if (!tenant || !selectedFile) {
      setErrorMessage("Select a DOCX file first.");
      return;
    }
    if (!uploadForm.partNumber || !uploadForm.title || !uploadForm.revisionNumber || !uploadForm.issueNumber) {
      setErrorMessage("Part number, title, revision number, and issue number are required.");
      return;
    }
    setUploading(true);
    setErrorMessage("");
    try {
      const result = await uploadDocxRevision(tenant, {
        code: uploadForm.partNumber,
        title: uploadForm.title,
        rev_number: uploadForm.revisionNumber,
        issue_number: uploadForm.issueNumber,
        effective_date: uploadForm.effectiveDate || undefined,
        manual_type: uploadForm.manualType,
        owner_role: uploadForm.ownerRole,
        change_log: uploadForm.changeLog,
        file: selectedFile,
      });
      resetUploadState();
      refresh();
      navigate(`${basePath}/${result.manual_id}/rev/${result.revision_id}/read`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <ManualsPageLayout
      title="Technical Publications"
      actions={
        <div className="manuals-dashboard-actions">
          <button className="manuals-ghost-btn" type="button" onClick={() => navigate(`${basePath}/master-list`)}>
            Master list
          </button>
          {canWrite ? (
            <button className="manuals-primary-btn" type="button" onClick={() => setUploadOpen(true)}>
              <UploadCloud size={16} /> Upload
            </button>
          ) : null}
        </div>
      }
    >
      <section className="manuals-hero-card">
        <div>
          <span className="manuals-eyebrow">Zero state</span>
          <h2>Upload master manual</h2>
          <p>Bring in the approved DOCX source, capture the initial metadata, and open the draft directly in the reader for controlled review.</p>
        </div>
        {canWrite ? (
          <button className="manuals-primary-btn" type="button" onClick={() => setUploadOpen(true)}>
            <UploadCloud size={16} /> Upload
          </button>
        ) : null}
      </section>

      <section className="manuals-kpi-grid">
        <article className="manuals-kpi-card"><span>Total manuals</span><strong>{kpis.total}</strong></article>
        <article className="manuals-kpi-card"><span>Active</span><strong>{kpis.active}</strong></article>
        <article className="manuals-kpi-card"><span>Drafts</span><strong>{kpis.drafts}</strong></article>
        <article className="manuals-kpi-card"><span>Pending KCAA</span><strong>{kpis.pendingKcaa}</strong></article>
        <article className="manuals-kpi-card"><span>Pending acknowledgements</span><strong>{kpis.pendingAcks}</strong></article>
      </section>

      <section className="manuals-page-grid">
        <article className="manuals-panel-card">
          <div className="manuals-section-head">
            <div>
              <h3>Next actions</h3>
              <p>High-priority lifecycle items that need attention.</p>
            </div>
          </div>
          {nextActions.length ? (
            <div className="manuals-action-list">
              {nextActions.map((row) => (
                <button key={`${row.manual_id}-${row.current_revision || "none"}`} type="button" className="manuals-action-row" onClick={() => row.current_revision && navigate(`${basePath}/${row.manual_id}/rev/${row.current_revision}/read`)}>
                  <span>
                    <strong>{row.code}</strong>
                    <small>{row.title}</small>
                  </span>
                  <span>
                    <small>{row.current_status}</small>
                    <strong>{row.pending_ack_count} open</strong>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="manuals-empty-note">No pending actions. The library is currently stable.</p>
          )}
        </article>

        <article className="manuals-panel-card">
          <div className="manuals-section-head">
            <div>
              <h3>Most used manuals</h3>
              <p>The 3 most commonly opened manuals for quick access.</p>
            </div>
          </div>
          <div className="manuals-featured-grid">
            {featured.length ? (
              featured.map((item) => (
                <button key={item.manual_id} type="button" className="manuals-featured-card" onClick={() => item.current_revision && navigate(`${basePath}/${item.manual_id}/rev/${item.current_revision}/read`)}>
                  <span className="manuals-featured-code">{item.code}</span>
                  <strong>{item.title}</strong>
                  <small>{item.manual_type}</small>
                  <span className="manuals-featured-meta">Opened {item.open_count} time(s)</span>
                </button>
              ))
            ) : (
              <p className="manuals-empty-note">Usage will appear here once manuals begin to be opened through the reader.</p>
            )}
          </div>
        </article>
      </section>

      <section className="manuals-panel-card">
        <div className="manuals-section-head manuals-section-head--register">
          <div>
            <h3>Controlled library register</h3>
            <p>Select a manual from the register to open the reader directly.</p>
          </div>
          <label className="manuals-search-field">
            <FileSearch size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, title, type, or stage" />
          </label>
        </div>
        <div className="manuals-register-wrap">
          <table className="manuals-register-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Title</th>
                <th>Type</th>
                <th>Revision</th>
                <th>Status</th>
                <th>Acks</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length ? (
                filteredRows.map((row) => (
                  <tr key={row.manual_id}>
                    <td>{row.code}</td>
                    <td>{row.title}</td>
                    <td>{row.manual_type}</td>
                    <td>{row.current_revision || "—"}</td>
                    <td>{row.current_status}</td>
                    <td>{row.pending_ack_count}</td>
                    <td>
                      <div className="manuals-row-actions">
                        <button type="button" className="manuals-inline-btn" disabled={!row.current_revision} onClick={() => row.current_revision && navigate(`${basePath}/${row.manual_id}/rev/${row.current_revision}/read`)}>
                          <FolderOpen size={14} /> Open
                        </button>
                        <button type="button" className="manuals-inline-btn" disabled={!row.current_revision} onClick={() => row.current_revision && navigate(`${basePath}/${row.manual_id}/rev/${row.current_revision}/workflow`)}>
                          <Workflow size={14} /> Workflow
                        </button>
                        <button type="button" className="manuals-inline-btn" disabled={!row.current_revision} onClick={() => row.current_revision && navigate(`${basePath}/${row.manual_id}/rev/${row.current_revision}/diff`)}>
                          <GitCompareArrows size={14} /> Diff
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="manuals-empty-row">No manuals available for the current filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {uploadOpen ? (
        <div className="manuals-modal-backdrop" role="presentation" onClick={resetUploadState}>
          <div className="manuals-upload-modal" role="dialog" aria-modal="true" aria-label="Upload manual" onClick={(event) => event.stopPropagation()}>
            <div className="manuals-upload-modal__header">
              <div>
                <h3>Upload master manual</h3>
                <p>Metadata is extracted from the uploaded document and can be corrected before saving.</p>
              </div>
              <button type="button" className="manuals-ghost-btn" onClick={resetUploadState}>Close</button>
            </div>

            <div className="manuals-upload-modal__body">
              <section className="manuals-upload-form-block">
                <div className="manuals-upload-field-group">
                  <label>Source file</label>
                  <input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void onPickFile(event.target.files?.[0] || null)} />
                  <small>{selectedFile ? `${selectedFile.name}` : "Select the DOCX source to extract metadata and build the draft revision."}</small>
                </div>

                <div className="manuals-upload-grid">
                  <label>
                    <span>Part number</span>
                    <input value={uploadForm.partNumber} onChange={(event) => setUploadForm((prev) => ({ ...prev, partNumber: event.target.value }))} placeholder="SL/MTM/001" />
                  </label>
                  <label>
                    <span>Manual type</span>
                    <input value={uploadForm.manualType} onChange={(event) => setUploadForm((prev) => ({ ...prev, manualType: event.target.value }))} placeholder="MTM" />
                  </label>
                  <label className="manuals-upload-grid__wide">
                    <span>Title</span>
                    <input value={uploadForm.title} onChange={(event) => setUploadForm((prev) => ({ ...prev, title: event.target.value }))} placeholder="Maintenance Training Manual" />
                  </label>
                  <label>
                    <span>Revision number</span>
                    <input value={uploadForm.revisionNumber} onChange={(event) => setUploadForm((prev) => ({ ...prev, revisionNumber: event.target.value }))} placeholder="00" />
                  </label>
                  <label>
                    <span>Issue number</span>
                    <input value={uploadForm.issueNumber} onChange={(event) => setUploadForm((prev) => ({ ...prev, issueNumber: event.target.value }))} placeholder="00" />
                  </label>
                  <label>
                    <span>Effective date</span>
                    <input type="date" value={uploadForm.effectiveDate} onChange={(event) => setUploadForm((prev) => ({ ...prev, effectiveDate: event.target.value }))} />
                  </label>
                  <label>
                    <span>Owner role</span>
                    <input value={uploadForm.ownerRole} onChange={(event) => setUploadForm((prev) => ({ ...prev, ownerRole: event.target.value }))} placeholder="Library" />
                  </label>
                </div>

                <div className="manuals-upload-field-group">
                  <label>Upload note</label>
                  <textarea rows={5} value={uploadForm.changeLog} onChange={(event) => setUploadForm((prev) => ({ ...prev, changeLog: event.target.value }))} placeholder="Summarize the intake note or change log for this revision." />
                </div>

                {errorMessage ? <p className="manuals-error">{errorMessage}</p> : null}
                {statusMessage ? <p className="manuals-success">{statusMessage}</p> : null}
              </section>

              <aside className="manuals-upload-preview-panel">
                <div className="manuals-upload-preview-panel__head">
                  <strong>Readable preview</strong>
                  {previewLoading ? <span>Extracting…</span> : preview ? <span>{preview.paragraph_count} paragraph(s)</span> : null}
                </div>
                {preview ? (
                  <div className="manuals-preview-scroll">
                    <section className="manuals-preview-block">
                      <h4>Detected metadata</h4>
                      <dl>
                        <div><dt>Part number</dt><dd>{preview.metadata.part_number || "—"}</dd></div>
                        <div><dt>Manual type</dt><dd>{preview.metadata.manual_type || "—"}</dd></div>
                        <div><dt>Title</dt><dd>{preview.metadata.title || preview.heading}</dd></div>
                        <div><dt>Revision</dt><dd>{preview.metadata.revision_number || "—"}</dd></div>
                        <div><dt>Issue</dt><dd>{preview.metadata.issue_number || "—"}</dd></div>
                        <div><dt>Effective date</dt><dd>{preview.metadata.effective_date || "—"}</dd></div>
                      </dl>
                    </section>
                    <section className="manuals-preview-block">
                      <h4>Outline</h4>
                      {preview.outline.length ? (
                        <ol>
                          {preview.outline.map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}
                        </ol>
                      ) : (
                        <p>No section headings were detected in the uploaded document.</p>
                      )}
                    </section>
                    <section className="manuals-preview-block">
                      <h4>Excerpt</h4>
                      <div className="manuals-preview-excerpt">{preview.excerpt || preview.sample.join("\n\n")}</div>
                    </section>
                  </div>
                ) : (
                  <p className="manuals-empty-note">After you choose a DOCX file, the right panel shows readable metadata, the section outline, and a plain-language text excerpt.</p>
                )}
              </aside>
            </div>

            <div className="manuals-upload-modal__footer">
              <button type="button" className="manuals-ghost-btn" onClick={resetUploadState}>Cancel</button>
              <button type="button" className="manuals-primary-btn" disabled={uploading || previewLoading || !selectedFile} onClick={onUpload}>
                <UploadCloud size={16} /> {uploading ? "Uploading…" : "Upload"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </ManualsPageLayout>
  );
}
