import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileCheck2,
  FileSpreadsheet,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  UploadCloud,
  UserPlus,
  Wifi,
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
import { buildCanonicalRoute } from "../../app/canonicalRoutes";
import { getContext } from "../../services/auth";
import "../../styles/training-workbook-import.css";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCompleted?: (job: TrainingWorkbookImportJob) => void | Promise<void>;
}

const ACTIVE_STATUSES = new Set(["QUEUED", "PARSING", "QUEUED_COMMIT", "COMMITTING"]);

interface ImportActivity {
  key: string;
  stage: string;
  sheet?: string | null;
  label?: string | null;
  processed: number;
  observedAt: number;
}

interface PollRecoveryState {
  failures: number;
  message: string;
  retryAt: number;
}

function humanize(value: string | null | undefined): string {
  return String(value || "")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (match) => match.toUpperCase());
}

function decisionLabel(value: string): string {
  const labels: Record<string, string> = {
    CREATE_ACCOUNT: "Create inactive account for approval and onboarding",
    LINK_EXISTING_ACCOUNT: "Link the existing portal account to this personnel profile",
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
    RECOVERING_COMMIT: "Recovering interrupted commit",
    COMMITTING_COURSES: "Writing course catalogue",
    COMMITTING_PEOPLE: "Writing personnel and licences",
    COMMITTING_ROLE_GROUPS: "Writing applicability groups",
    COMMITTING_PERSON_ROLES: "Writing personnel role assignments",
    COMMITTING_COURSE_MATRIX: "Writing course requirement matrix",
    COMMITTING_TRAINING: "Writing training history",
    FINALIZING_COMMIT: "Finalizing atomic write",
    FINALIZING_IMPORT: "Publishing reconciliation",
    COMPLETED: "Import completed",
    FAILED: "Import failed",
    CANCELLED: "Import cancelled",
  };
  return labels[job.stage] || humanize(job.stage);
}

function stagePosition(stage: string): string {
  const commitStages = [
    "COMMITTING_COURSES",
    "COMMITTING_PEOPLE",
    "COMMITTING_ROLE_GROUPS",
    "COMMITTING_PERSON_ROLES",
    "COMMITTING_COURSE_MATRIX",
    "COMMITTING_TRAINING",
  ];
  const commitIndex = commitStages.indexOf(stage);
  if (commitIndex >= 0) return `Commit phase ${commitIndex + 1} of ${commitStages.length}`;
  if (stage === "QUEUED_COMMIT") return "Commit queued";
  if (stage === "RECOVERING_COMMIT") return "Automatic recovery queued";
  if (["FINALIZING_COMMIT", "FINALIZING_IMPORT"].includes(stage)) return "Commit phase 6 of 6";
  if (stage === "DISCOVERING_SHEETS") return "Preview phase 1 of 3";
  if (["VALIDATING", "MATCHING"].includes(stage)) return "Preview phase 2 of 3";
  if (stage === "REVIEW") return "Preview phase 3 of 3";
  return humanize(stage);
}

function ageLabel(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  if (seconds < 2) return "now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s ago`;
}

function retryDelayLabel(milliseconds: number): string {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return seconds <= 1 ? "now" : `in ${seconds}s`;
}

function clockLabel(value: number): string {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function summaryNumber(job: TrainingWorkbookImportJob | null, key: string): number {
  const stats = job?.summary?.commit_stats;
  if (!stats || typeof stats !== "object") return 0;
  const value = (stats as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function rootSummaryNumber(job: TrainingWorkbookImportJob | null, key: string): number {
  const value = job?.summary?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function payloadText(row: TrainingWorkbookImportRow, key: string): string {
  const value = row.payload?.[key];
  return value == null ? "" : String(value).trim();
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

async function loadAllImportRows(
  jobId: string,
  options: { reviewOnly?: boolean; status?: string },
): Promise<TrainingWorkbookImportRow[]> {
  const limit = 250;
  const items: TrainingWorkbookImportRow[] = [];
  let offset = 0;
  while (true) {
    const page = await listTrainingWorkbookImportRows(jobId, { ...options, limit, offset });
    items.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || page.items.length === 0) return items;
  }
}

const TrainingWorkbookImportDialog: React.FC<Props> = ({ isOpen, onClose, onCompleted }) => {
  const navigate = useNavigate();
  const amoCode = getContext().amoCode || "UNKNOWN";
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<TrainingWorkbookImportJob | null>(null);
  const [uploadProgress, setUploadProgress] = useState<WorkbookUploadProgress | null>(null);
  const [uploading, setUploading] = useState(false);
  const [activity, setActivity] = useState<ImportActivity[]>([]);
  const [reviewRows, setReviewRows] = useState<TrainingWorkbookImportRow[]>([]);
  const [issueRows, setIssueRows] = useState<TrainingWorkbookImportRow[]>([]);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [selectedSheet, setSelectedSheet] = useState("ALL");
  const [error, setError] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [forceReimport, setForceReimport] = useState(false);
  const [lastServerCheckAt, setLastServerCheckAt] = useState<number | null>(null);
  const [pollRecovery, setPollRecovery] = useState<PollRecoveryState | null>(null);
  const [pollNonce, setPollNonce] = useState(0);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const completionNotifiedRef = useRef<string | null>(null);
  const activityKeyRef = useRef<string | null>(null);

  const busy = uploading || committing || Boolean(job && ACTIVE_STATUSES.has(job.status));
  const processed = job?.processed_rows || 0;
  const total = job?.total_rows || 0;
  const processingPercent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : uploadProgress?.percent ? Math.round(uploadProgress.percent) : 0;
  const workerCheckpointAt = job?.updated_at ? new Date(job.updated_at).getTime() : null;
  const workerCheckpointAge = workerCheckpointAt ? Math.max(0, clockNow - workerCheckpointAt) : 0;
  const serverCheckAge = lastServerCheckAt ? Math.max(0, clockNow - lastServerCheckAt) : 0;
  const workerCheckpointStale = Boolean(job && ACTIVE_STATUSES.has(job.status) && workerCheckpointAt && workerCheckpointAge >= 15_000);
  const portalAccountsCreated = summaryNumber(job, "portal_accounts_created");
  const personnelProfilesCreated = summaryNumber(job, "personnel_profiles_created");
  const nonLoginIdentitiesCreated = summaryNumber(job, "non_login_identities_created");
  const commitElapsedMs = summaryNumber(job, "elapsed_ms");
  const automaticRecoveryAttempts = rootSummaryNumber(job, "automatic_recovery_attempts");
  const previewCompleted = Boolean(job && job.sheets.length > 0 && job.total_rows > 0);
  const isRetryableFailure = job?.status === "FAILED" && previewCompleted;
  const isReviewReady = job?.status === "PREVIEW_READY" || job?.status === "REVIEW_REQUIRED" || isRetryableFailure;
  const unresolvedDecisions = reviewRows.filter((row) => row.decision_required && !decisions[row.id]).length;
  const createdAccountRows = useMemo(
    () => reviewRows.filter((row) => row.decision === "CREATE_ACCOUNT" && Boolean(row.committed_entity_id)),
    [reviewRows],
  );
  const createdAccountOutcomeCount = Math.max(portalAccountsCreated, createdAccountRows.length);

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
    setActivity([]);
    setReviewRows([]);
    setIssueRows([]);
    setDecisions({});
    setQuery("");
    setSelectedSheet("ALL");
    setError(null);
    setCommitting(false);
    setForceReimport(false);
    setLastServerCheckAt(null);
    setPollRecovery(null);
    setPollNonce(0);
    completionNotifiedRef.current = null;
    activityKeyRef.current = null;
  };

  const openCreatedAccount = (row: TrainingWorkbookImportRow) => {
    if (!row.committed_entity_id) return;
    onClose();
    navigate(buildCanonicalRoute.adminUserDetail({ amoCode, userId: row.committed_entity_id }));
  };

  useEffect(() => {
    if (!isOpen) reset();
  }, [isOpen]);

  useEffect(() => {
    if (!job || !ACTIVE_STATUSES.has(job.status)) return;
    let stopped = false;
    let timer: number | null = null;
    let consecutiveFailures = 0;
    const poll = async () => {
      let continuePolling = true;
      let nextDelay = document.visibilityState === "hidden" ? 2_500 : 900;
      try {
        const next = await getTrainingWorkbookImport(job.id);
        if (stopped) return;
        consecutiveFailures = 0;
        setPollRecovery(null);
        setLastServerCheckAt(Date.now());
        setJob(next);
        const activityKey = [next.stage, next.current_sheet || "", next.current_record_label || "", next.processed_rows].join("|");
        if (ACTIVE_STATUSES.has(next.status) && activityKeyRef.current !== activityKey) {
          activityKeyRef.current = activityKey;
          setActivity((current) => [{
            key: `${activityKey}|${Date.now()}`,
            stage: next.stage,
            sheet: next.current_sheet,
            label: next.current_record_label,
            processed: next.processed_rows,
            observedAt: Date.now(),
          }, ...current].slice(0, 6));
        }
        continuePolling = ACTIVE_STATUSES.has(next.status);
      } catch (pollError) {
        consecutiveFailures += 1;
        nextDelay = Math.min(12_000, 900 * (2 ** Math.min(4, consecutiveFailures - 1)));
        if (!stopped) {
          setPollRecovery({
            failures: consecutiveFailures,
            message: pollError instanceof Error ? pollError.message : "Could not refresh import progress.",
            retryAt: Date.now() + nextDelay,
          });
        }
      } finally {
        if (!stopped && continuePolling) {
          timer = window.setTimeout(() => void poll(), nextDelay);
        }
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [job?.id, job?.status, pollNonce]);

  useEffect(() => {
    if (!job || !ACTIVE_STATUSES.has(job.status)) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (!job || !["PREVIEW_READY", "REVIEW_REQUIRED", "COMPLETED", "FAILED"].includes(job.status)) return;
    let active = true;
    const loadRows = async () => {
      try {
        const [allReviewRows, allIssueRows] = await Promise.all([
          loadAllImportRows(job.id, { reviewOnly: true }),
          loadAllImportRows(job.id, { status: "FAILED" }),
        ]);
        if (!active) return;
        setReviewRows(allReviewRows);
        setIssueRows(allIssueRows);
        setDecisions((current) => {
          const next = { ...current };
          allReviewRows.forEach((row) => {
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
  }, [job?.id, job?.status]);

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
    setActivity([]);
    setLastServerCheckAt(null);
    activityKeyRef.current = null;
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
                {ACTIVE_STATUSES.has(job.status) ? (
                  <div className="training-import-status__telemetry" aria-label="Live import telemetry">
                    <span><Activity size={14} /> {stagePosition(job.stage)}</span>
                    <span className={workerCheckpointStale ? "is-stale" : ""}><Clock3 size={14} /> Worker checkpoint {ageLabel(workerCheckpointAge)}</span>
                    <span><Wifi size={14} /> Server checked {lastServerCheckAt ? ageLabel(serverCheckAge) : "waiting"}</span>
                  </div>
                ) : null}
              </div>
              <div className="training-import-status__count">
                <strong>{processingPercent}%</strong>
                <span>{processed.toLocaleString()} of {total.toLocaleString()} rows</span>
              </div>
              <div className="training-import-progress__bar training-import-progress__bar--wide"><span style={{ width: `${processingPercent}%` }} /></div>
            </section>

            {pollRecovery ? (
              <div className="training-import-alert training-import-alert--warning training-import-alert--recovering">
                <AlertTriangle size={18} />
                <span>
                  The status server is temporarily unavailable. Progress has not been guessed or discarded;
                  automatic check {retryDelayLabel(pollRecovery.retryAt - clockNow)} (attempt {pollRecovery.failures + 1}).
                  <small>{pollRecovery.message}</small>
                </span>
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => {
                    setPollRecovery(null);
                    setPollNonce((value) => value + 1);
                  }}
                >
                  <RefreshCw size={15} /> Check now
                </button>
              </div>
            ) : null}

            {workerCheckpointStale ? (
              <div className="training-import-alert training-import-alert--warning">
                <AlertTriangle size={18} />
                <span>
                  No new worker checkpoint has been published for {ageLabel(workerCheckpointAge).replace(" ago", "")}.
                  The server keeps checking and automatically renews an orphaned commit lease after the recovery threshold—no re-upload is required.
                  {automaticRecoveryAttempts > 0 ? ` Recovery attempt ${automaticRecoveryAttempts} is active.` : ""}
                </span>
              </div>
            ) : null}

            {job.duplicate_of_job_id ? (
              <div className="training-import-alert training-import-alert--warning">
                <AlertTriangle size={18} />
                <span>This exact workbook was committed before. Review the reconciliation and enable force re-import only when the repeated migration is intentional.</span>
              </div>
            ) : null}

            {isRetryableFailure && job.error_message ? (
              <div className="training-import-alert training-import-alert--danger">
                <AlertTriangle size={18} />
                <span>The reviewed commit failed and can be retried. {job.error_message}</span>
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

            {job.status === "COMPLETED" ? (
              <section className="training-import-completion" aria-label="Completed import outcome">
                <div className="training-import-complete">
                  <FileCheck2 size={24} />
                  <div>
                    <strong>Import completed successfully</strong>
                    <span>
                      The atomic commit finished{job.committed_at ? ` at ${new Date(job.committed_at).toLocaleString()}` : ""}.
                      {commitElapsedMs > 0 ? ` Server write time: ${(commitElapsedMs / 1000).toFixed(1)} seconds.` : ""}
                    </span>
                  </div>
                </div>

                <div className="training-import-outcome-grid">
                  <div><span>Personnel profiles</span><strong>{personnelProfilesCreated.toLocaleString()}</strong><small>Created from accepted People rows</small></div>
                  <div><span>Portal accounts</span><strong>{createdAccountOutcomeCount.toLocaleString()}</strong><small>Inactive, awaiting administrator onboarding</small></div>
                  <div><span>Non-login identities</span><strong>{nonLoginIdentitiesCreated.toLocaleString()}</strong><small>Retained for governed personnel records</small></div>
                  <div><span>Job reference</span><strong>{job.id}</strong><small>Use this reference for audit or support</small></div>
                </div>

                {createdAccountOutcomeCount > 0 ? (
                  <div className="training-import-account-review">
                    <div className="training-import-section__header">
                      <div>
                        <h4>New accounts awaiting onboarding</h4>
                        <p>Review identity, department and role before enabling access. Each account remains disabled until an administrator opens and approves it.</p>
                      </div>
                      <UserPlus size={20} />
                    </div>
                    <div className="training-import-password-policy">
                      <KeyRound size={18} />
                      <span><strong>No default password is issued or displayed.</strong> A random unknown credential blocks initial sign-in. After approving and enabling the account, the user must request the secure password-reset link and choose their own password.</span>
                    </div>
                    {createdAccountRows.length > 0 ? (
                      <div className="training-import-account-list">
                        {createdAccountRows.map((row) => {
                          const fullName = row.display_label || payloadText(row, "full_name") || [payloadText(row, "first_name"), payloadText(row, "last_name")].filter(Boolean).join(" ") || "Imported account";
                          const staffCode = payloadText(row, "person_id") || row.source_key || "No staff code";
                          const email = payloadText(row, "email") || "No email supplied";
                          return (
                            <div key={row.id}>
                              <div><strong>{fullName}</strong><span>{staffCode} · {email}</span></div>
                              <span className="training-import-account-state">Pending activation</span>
                              <button type="button" className="secondary-chip-btn" onClick={() => openCreatedAccount(row)}>
                                Review <ArrowRight size={15} />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="training-import-account-loading">The account total was committed; refresh this job to load the individual onboarding links.</p>
                    )}
                  </div>
                ) : null}
              </section>
            ) : null}

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

            {ACTIVE_STATUSES.has(job.status) && activity.length > 0 ? (
              <section className="training-import-section">
                <div className="training-import-section__header"><div><h4>Processing now</h4><p>Server-confirmed checkpoints; no simulated progress.</p></div></div>
                <div className="training-import-live-list">
                  {activity.map((item) => (
                    <div key={item.key}>
                      <span>{clockLabel(item.observedAt)}</span>
                      <strong>{item.sheet ? `${item.sheet}${item.label ? ` · ${item.label}` : ""}` : stageLabel({ ...job, stage: item.stage })}</strong>
                      <small>{item.processed.toLocaleString()} rows · {humanize(item.stage)}</small>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {isReviewReady && reviewRows.length > 0 ? (
              <section className="training-import-section training-import-review">
                <div className="training-import-section__header">
                  <div><h4>Personnel and conflict review</h4><p>New people are never silently activated. Create an inactive account for approval, link an existing account when identified, keep a non-login personnel identity, or skip the row.</p></div>
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

          </>
        )}

        {error ? <div className="training-import-alert training-import-alert--danger"><XCircle size={18} /><span>{error}</span></div> : null}

        <footer className="training-import-actions">
          <button type="button" className={job?.status === "COMPLETED" ? "primary-chip-btn" : "secondary-chip-btn"} onClick={requestClose} disabled={busy}>{job?.status === "COMPLETED" ? "Done" : "Close"}</button>
          {job && ACTIVE_STATUSES.has(job.status) ? <button type="button" className="secondary-chip-btn" onClick={() => void cancel()}>Cancel job</button> : null}
          {!job ? (
            <button type="button" className="primary-chip-btn" onClick={() => void upload()} disabled={!file || uploading}>
              {uploading ? "Uploading…" : "Inspect workbook"}
            </button>
          ) : isReviewReady ? (
            <>
              {job.duplicate_of_job_id ? <label className="training-import-force"><input type="checkbox" checked={forceReimport} onChange={(event) => setForceReimport(event.target.checked)} /> Force reviewed re-import</label> : null}
              <button type="button" className="primary-chip-btn" onClick={() => void commit()} disabled={committing || unresolvedDecisions > 0}>
                {committing ? "Starting import…" : isRetryableFailure ? "Retry reviewed import" : `Commit ${Math.max(0, total - job.failed_count - job.skipped_count).toLocaleString()} reviewed rows`}
              </button>
            </>
          ) : null}
        </footer>
      </div>
    </Drawer>
  );
};

export default TrainingWorkbookImportDialog;
