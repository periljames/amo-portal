import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  FileSpreadsheet,
  LoaderCircle,
  Search,
  ShieldCheck,
  UploadCloud,
  UserPlus,
  XCircle,
} from "lucide-react";
import Drawer from "../shared/Drawer";
import {
  cancelTrainingWorkbookImport,
  commitTrainingWorkbookImport,
  createTrainingWorkbookImport,
  getTrainingWorkbookImport,
  listTrainingWorkbookImportRows,
  type WorkbookUploadProgress,
} from "../../services/trainingWorkbookImport";
import type {
  TrainingWorkbookImportDecision,
  TrainingWorkbookImportJob,
  TrainingWorkbookImportRow,
} from "../../types/trainingWorkbookImport";
import "../../styles/training-workbook-import.css";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCompleted?: (job: TrainingWorkbookImportJob) => void | Promise<void>;
}

const ACTIVE_STATUSES = new Set(["QUEUED", "PARSING", "QUEUED_COMMIT", "COMMITTING"]);

function humanize(value: string | null | undefined): string {
  return String(value || "")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (match) => match.toUpperCase());
}

function decisionLabel(value: string): string {
  const labels: Record<string, string> = {
    CREATE_ACCOUNT: "Create personnel profile and portal account",
    PROFILE_ONLY: "Accept personnel record without portal access",
    SKIP: "Do not import this row",
    KEEP_EXISTING_EMAIL: "Keep existing email and update other fields",
    USE_IMPORTED_EMAIL: "Use workbook email",
    RETRY_AFTER_PERSON_IMPORT: "Retry after accepted People rows are created",
  };
  return labels[value] || humanize(value);
}

function stageLabel(job: TrainingWorkbookImportJob | null): string {
  if (!job) return "Select a workbook";
  const labels: Record<string, string> = {
    UPLOAD_COMPLETE: "Workbook uploaded",
    DISCOVERING_SHEETS: "Discovering worksheets",
    VALIDATING: "Validating workbook rows",
    MATCHING: "Matching personnel and courses",
    REVIEW: "Review import decisions",
    QUEUED_COMMIT: "Preparing controlled import",
    COMMITTING_COURSES: "Writing course catalogue",
    COMMITTING_PEOPLE: "Writing personnel and licences",
    COMMITTING_TRAINING: "Writing training history",
    COMPLETED: "Import completed",
    FAILED: "Import failed",
    CANCELLED: "Import cancelled",
  };
  return labels[job.stage] || humanize(job.stage);
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function statusTone(status: string): string {
  if (["FAILED", "REVIEW"].includes(status)) return "danger";
  if (["COMPLETED", "COMMITTED", "READY"].includes(status)) return "success";
  if (["SKIPPED", "CANCELLED"].includes(status)) return "muted";
  return "info";
}

const TrainingWorkbookImportDialog: React.FC<Props> = ({ isOpen, onClose, onCompleted }) => {
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<TrainingWorkbookImportJob | null>(null);
  const [uploadProgress, setUploadProgress] = useState<WorkbookUploadProgress | null>(null);
  const [uploading, setUploading] = useState(false);
  const [recentRows, setRecentRows] = useState<TrainingWorkbookImportRow[]>([]);
  const [reviewRows, setReviewRows] = useState<TrainingWorkbookImportRow[]>([]);
  const [issueRows, setIssueRows] = useState<TrainingWorkbookImportRow[]>([]);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [selectedSheet, setSelectedSheet] = useState("ALL");
  const [error, setError] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [forceReimport, setForceReimport] = useState(false);
  const completionNotifiedRef = useRef<string | null>(null);

  const busy = uploading || committing || Boolean(job && ACTIVE_STATUSES.has(job.status));
  const processed = job?.processed_rows || 0;
  const total = job?.total_rows || 0;
  const processingPercent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : uploadProgress?.percent ? Math.round(uploadProgress.percent) : 0;
  const isReviewReady = job?.status === "PREVIEW_READY" || job?.status === "REVIEW_REQUIRED";
  const unresolvedDecisions = reviewRows.filter((row) => row.decision_required && !decisions[row.id]).length;

  const filteredReviewRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return reviewRows.filter((row) => {
      if (selectedSheet !== "ALL" && row.sheet_name !== selectedSheet) return false;
      if (!needle) return true;
      return [row.display_label, row.source_key, row.issue_message, row.sheet_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [query, reviewRows, selectedSheet]);

  const reset = () => {
    setFile(null);
    setJob(null);
    setUploadProgress(null);
    setUploading(false);
    setRecentRows([]);
    setReviewRows([]);
    setIssueRows([]);
    setDecisions({});
    setQuery("");
    setSelectedSheet("ALL");
    setError(null);
    setCommitting(false);
    setForceReimport(false);
    completionNotifiedRef.current = null;
  };

  useEffect(() => {
    if (!isOpen) reset();
  }, [isOpen]);

  useEffect(() => {
    if (!job || !ACTIVE_STATUSES.has(job.status)) return;
    let stopped = false;
    const poll = async () => {
      try {
        const next = await getTrainingWorkbookImport(job.id);
        if (stopped) return;
        setJob(next);
        const offset = Math.max(0, (next.processed_rows || 0) - 8);
        const page = await listTrainingWorkbookImportRows(next.id, { limit: 8, offset });
        if (!stopped) setRecentRows(page.items);
      } catch (pollError) {
        if (!stopped) setError(pollError instanceof Error ? pollError.message : "Could not refresh import progress.");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 700);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (!job || !["PREVIEW_READY", "REVIEW_REQUIRED", "COMPLETED", "FAILED"].includes(job.status)) return;
    let active = true;
    const loadRows = async () => {
      try {
        const [reviewPage, issuePage] = await Promise.all([
          listTrainingWorkbookImportRows(job.id, { reviewOnly: true, limit: 250 }),
          listTrainingWorkbookImportRows(job.id, { status: "FAILED", limit: 250 }),
        ]);
        if (!active) return;
        setReviewRows(reviewPage.items);
        setIssueRows(issuePage.items);
        setDecisions((current) => {
          const next = { ...current };
          reviewPage.items.forEach((row) => {
            if (row.decision) next[row.id] = row.decision;
          });
          return next;
        });
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : "Could not load import review rows.");
      }
    };
    void loadRows();
    return () => {
      active = false;
    };
  }, [job?.id, job?.status, job?.updated_at]);

  useEffect(() => {
    if (!job || job.status !== "COMPLETED" || completionNotifiedRef.current === job.id) return;
    completionNotifiedRef.current = job.id;
    void onCompleted?.(job);
  }, [job, onCompleted]);

  const upload = async () => {
    if (!file) {
      setError("Choose the Training Tracker workbook first.");
      return;
    }
    setUploading(true);
    setError(null);
    setJob(null);
    setUploadProgress(null);
    setRecentRows([]);
    setReviewRows([]);
    setIssueRows([]);
    setDecisions({});
    try {
      const created = await createTrainingWorkbookImport(file, {
        idempotencyKey: `training-workbook:${crypto.randomUUID()}`,
        onUploadProgress: setUploadProgress,
      });
      setJob(created);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Workbook upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const commit = async () => {
    if (!job) return;
    if (unresolvedDecisions > 0) {
      setError(`Resolve ${unresolvedDecisions} personnel or conflict decision(s) before importing.`);
      return;
    }
    setCommitting(true);
    setError(null);
    try {
      const payload: TrainingWorkbookImportDecision[] = Object.entries(decisions).map(([row_id, decision]) => ({ row_id, decision }));
      const next = await commitTrainingWorkbookImport(job.id, payload, forceReimport);
      setJob(next);
    } catch (commitError) {
      setError(commitError instanceof Error ? commitError.message : "The controlled import could not start.");
    } finally {
      setCommitting(false);
    }
  };

  const cancel = async () => {
    if (!job) return;
    try {
      setJob(await cancelTrainingWorkbookImport(job.id));
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Could not cancel the import.");
    }
  };

  const requestClose = () => {
    if (busy) return;
    onClose();
  };

  return (
    <Drawer
      title="Import training workbook"
      isOpen={isOpen}
      onClose={requestClose}
      closeDisabled={busy}
      panelClassName="training-workbook-import-dialog"
    >
      <div className="training-import-shell">
        {!job ? (
          <section className="training-import-upload">
            <div className="training-import-upload__icon"><FileSpreadsheet size={30} /></div>
            <div>
              <h4>Bring the complete tracker into the portal</h4>
              <p>Courses, People, Training, role groups, person roles and the course matrix are inspected together. Derived Excel dashboards are mapped to live portal views rather than copied as duplicate data.</p>
            </div>
            <label className="training-import-dropzone">
              <UploadCloud size={22} />
              <span>{file ? file.name : "Choose Training_Tracker_DB_v2.xlsm or another compatible workbook"}</span>
              <small>{file ? formatBytes(file.size) : "Excel .xlsx or .xlsm · maximum 40 MB"}</small>
              <input
                type="file"
                accept=".xlsx,.xlsm,.xltx,.xltm"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
                disabled={uploading}
              />
            </label>
            {uploadProgress ? (
              <div className="training-import-progress training-import-progress--upload">
                <div className="training-import-progress__bar"><span style={{ width: `${Math.round(uploadProgress.percent || 0)}%` }} /></div>
                <strong>{Math.round(uploadProgress.percent || 0)}%</strong>
                <span>{formatBytes(uploadProgress.loadedBytes)}{uploadProgress.totalBytes ? ` of ${formatBytes(uploadProgress.totalBytes)}` : ""} transferred</span>
              </div>
            ) : null}
          </section>
        ) : (
          <>
            <section className={`training-import-status training-import-status--${statusTone(job.status)}`}>
              <div className="training-import-orbit" style={{ "--import-progress": `${processingPercent * 3.6}deg` } as React.CSSProperties}>
                {job.status === "COMPLETED" ? <CheckCircle2 size={30} /> : job.status === "FAILED" ? <XCircle size={30} /> : <LoaderCircle size={30} />}
              </div>
              <div className="training-import-status__copy">
                <span className="training-import-status__eyebrow">{job.filename}</span>
                <h4>{stageLabel(job)}</h4>
                <p>{job.current_sheet ? `${job.current_sheet}${job.current_record_label ? ` · ${job.current_record_label}` : ""}` : "Workbook control job is ready."}</p>
              </div>
              <div className="training-import-status__count">
                <strong>{processingPercent}%</strong>
                <span>{processed.toLocaleString()} of {total.toLocaleString()} rows</span>
              </div>
              <div className="training-import-progress__bar training-import-progress__bar--wide"><span style={{ width: `${processingPercent}%` }} /></div>
            </section>

            {job.duplicate_of_job_id ? (
              <div className="training-import-alert training-import-alert--warning">
                <AlertTriangle size={18} />
                <span>This exact workbook was committed before. Review the reconciliation and enable force re-import only when the repeated migration is intentional.</span>
              </div>
            ) : null}

            <section className="training-import-metrics" aria-label="Import reconciliation">
              {[
                ["Create", job.created_count],
                ["Update", job.updated_count],
                ["Unchanged", job.unchanged_count],
                ["Review", job.review_count],
                ["Skipped", job.skipped_count],
                ["Failed", job.failed_count],
              ].map(([label, value]) => (
                <div key={String(label)}><span>{label}</span><strong>{Number(value).toLocaleString()}</strong></div>
              ))}
            </section>

            {job.sheets.length > 0 ? (
              <section className="training-import-section">
                <div className="training-import-section__header">
                  <div><h4>Workbook functions</h4><p>Every sheet has an explicit portal destination.</p></div>
                  <ShieldCheck size={20} />
                </div>
                <div className="training-import-sheet-grid">
                  {job.sheets.map((sheet) => (
                    <button
                      type="button"
                      key={sheet.id}
                      className={`training-import-sheet ${selectedSheet === sheet.sheet_name ? "is-active" : ""}`}
                      onClick={() => setSelectedSheet((current) => current === sheet.sheet_name ? "ALL" : sheet.sheet_name)}
                    >
                      <span className="training-import-sheet__name">{sheet.sheet_name}</span>
                      <strong>{sheet.portal_destination}</strong>
                      <small>{sheet.is_operational ? `${sheet.processed_rows || sheet.total_rows} rows · ${humanize(sheet.status)}` : "Live portal view"}</small>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            {ACTIVE_STATUSES.has(job.status) && recentRows.length > 0 ? (
              <section className="training-import-section">
                <div className="training-import-section__header"><div><h4>Processing now</h4><p>Most recently inspected records.</p></div></div>
                <div className="training-import-live-list">
                  {recentRows.map((row) => (
                    <div key={row.id}>
                      <span>{row.sheet_name} · row {row.source_row}</span>
                      <strong>{row.display_label || row.source_key || "Workbook record"}</strong>
                      <small>{humanize(row.proposed_action)}</small>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {isReviewReady && reviewRows.length > 0 ? (
              <section className="training-import-section training-import-review">
                <div className="training-import-section__header">
                  <div><h4>Personnel and conflict review</h4><p>New people are never silently given portal access. Accept each as a user, personnel-only record, or skip it.</p></div>
                  <UserPlus size={20} />
                </div>
                <div className="training-import-filterbar">
                  <label><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, staff code or issue" /></label>
                  <span>{unresolvedDecisions} decision{unresolvedDecisions === 1 ? "" : "s"} remaining</span>
                </div>
                <div className="training-import-table-wrap">
                  <table className="training-import-table">
                    <thead><tr><th>Workbook row</th><th>Record</th><th>Reason</th><th>Decision</th></tr></thead>
                    <tbody>
                      {filteredReviewRows.map((row) => (
                        <tr key={row.id}>
                          <td>{row.sheet_name} · {row.source_row}</td>
                          <td><strong>{row.display_label || row.source_key || "Record"}</strong><small>{row.source_key}</small></td>
                          <td>{row.issue_message || humanize(row.proposed_action)}</td>
                          <td>
                            <select
                              value={decisions[row.id] || ""}
                              onChange={(event) => setDecisions((current) => ({ ...current, [row.id]: event.target.value }))}
                            >
                              <option value="">Select decision</option>
                              {row.decision_options.map((option) => <option key={option} value={option}>{decisionLabel(option)}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}

            {issueRows.length > 0 ? (
              <details className="training-import-issues" open={job.status === "FAILED"}>
                <summary><AlertTriangle size={17} /> {issueRows.length} row issue{issueRows.length === 1 ? "" : "s"}</summary>
                <div className="training-import-table-wrap">
                  <table className="training-import-table">
                    <thead><tr><th>Location</th><th>Record</th><th>Issue</th></tr></thead>
                    <tbody>{issueRows.map((row) => <tr key={row.id}><td>{row.sheet_name} · {row.source_row}</td><td>{row.display_label || row.source_key || "—"}</td><td>{row.issue_message || row.issue_code || "Validation failed"}</td></tr>)}</tbody>
                  </table>
                </div>
              </details>
            ) : null}

            {job.status === "COMPLETED" ? (
              <div className="training-import-complete">
                <FileCheck2 size={24} />
                <div><strong>Training handler updated</strong><span>Personnel, licences, courses, role assignments, matrix rules and training history were reconciled under one audited import.</span></div>
              </div>
            ) : null}
          </>
        )}

        {error ? <div className="training-import-alert training-import-alert--danger"><XCircle size={18} /><span>{error}</span></div> : null}

        <footer className="training-import-actions">
          <button type="button" className="secondary-chip-btn" onClick={requestClose} disabled={busy}>Close</button>
          {job && ACTIVE_STATUSES.has(job.status) ? <button type="button" className="secondary-chip-btn" onClick={() => void cancel()}>Cancel job</button> : null}
          {!job ? (
            <button type="button" className="primary-chip-btn" onClick={() => void upload()} disabled={!file || uploading}>
              {uploading ? "Uploading…" : "Inspect workbook"}
            </button>
          ) : isReviewReady ? (
            <>
              {job.duplicate_of_job_id ? <label className="training-import-force"><input type="checkbox" checked={forceReimport} onChange={(event) => setForceReimport(event.target.checked)} /> Force reviewed re-import</label> : null}
              <button type="button" className="primary-chip-btn" onClick={() => void commit()} disabled={committing || unresolvedDecisions > 0}>
                {committing ? "Starting import…" : `Commit ${Math.max(0, total - job.failed_count - job.skipped_count).toLocaleString()} reviewed rows`}
              </button>
            </>
          ) : null}
        </footer>
      </div>
    </Drawer>
  );
};

export default TrainingWorkbookImportDialog;
