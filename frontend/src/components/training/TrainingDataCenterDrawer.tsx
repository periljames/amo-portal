import React, { useMemo, useState } from "react";
import {
  BookOpenCheck,
  Download,
  FileSpreadsheet,
  FileUp,
  GraduationCap,
  ListPlus,
  Loader2,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

import Drawer from "../shared/Drawer";
import { importTrainingCoursesWorkbook, importTrainingRecordsWorkbook } from "../../services/training";
import type { CourseImportSummary, TrainingRecordImportSummary } from "../../types/training";
import "../../styles/training-data-centre.css";

type TargetedImport = "courses" | "records";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  canManage: boolean;
  onOpenFullWorkbook: () => void;
  onCreateCourse: () => void;
  onCreateRequirement: () => void;
  onOpenGovernanceForms: () => void;
  onExportCourses: () => void;
  onExportTraining: () => void;
  onCommitted: () => void | Promise<void>;
};

type ImportSummary = CourseImportSummary | TrainingRecordImportSummary;

const acceptedWorkbookTypes = ".xlsx,.xlsm,.xltx,.xltm";

function summaryCount(summary: ImportSummary | null, key: "created" | "updated" | "skipped"): number {
  return Number(summary?.[key] || 0);
}

const TrainingDataCenterDrawer: React.FC<Props> = ({
  isOpen,
  onClose,
  canManage,
  onOpenFullWorkbook,
  onCreateCourse,
  onCreateRequirement,
  onOpenGovernanceForms,
  onExportCourses,
  onExportTraining,
  onCommitted,
}) => {
  const [courseFile, setCourseFile] = useState<File | null>(null);
  const [recordFile, setRecordFile] = useState<File | null>(null);
  const [courseSheet, setCourseSheet] = useState("Courses");
  const [recordSheet, setRecordSheet] = useState("Training");
  const [courseSummary, setCourseSummary] = useState<ImportSummary | null>(null);
  const [recordSummary, setRecordSummary] = useState<ImportSummary | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isBusy = Boolean(busyAction);
  const issueCount = useMemo(
    () => [...(courseSummary?.errors || []), ...(recordSummary?.errors || [])].length,
    [courseSummary, recordSummary],
  );

  const runTargetedImport = async (kind: TargetedImport, dryRun: boolean) => {
    const file = kind === "courses" ? courseFile : recordFile;
    const sheetName = kind === "courses" ? courseSheet : recordSheet;
    if (!file) {
      setError(`Choose the ${kind === "courses" ? "course catalogue" : "training records"} Excel file first.`);
      return;
    }
    setBusyAction(`${kind}:${dryRun ? "preview" : "commit"}`);
    setError(null);
    setNotice(null);
    try {
      const summary = kind === "courses"
        ? await importTrainingCoursesWorkbook(file, { dryRun, sheetName })
        : await importTrainingRecordsWorkbook(file, { dryRun, sheetName });
      if (kind === "courses") setCourseSummary(summary);
      else setRecordSummary(summary);
      if (dryRun) {
        setNotice(`${kind === "courses" ? "Course catalogue" : "Training history"} preview is ready. Review the counts before committing.`);
      } else {
        setNotice(`${kind === "courses" ? "Course catalogue" : "Training history"} imported successfully.`);
        await onCommitted();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The Excel import could not be completed.");
    } finally {
      setBusyAction(null);
    }
  };

  const openFullWorkbook = () => {
    onClose();
    onOpenFullWorkbook();
  };

  const openPortalForm = (action: () => void) => {
    onClose();
    action();
  };

  const renderSummary = (summary: ImportSummary | null) => summary ? (
    <div className="training-data-centre__summary" aria-live="polite">
      <span><strong>{summaryCount(summary, "created")}</strong> create</span>
      <span><strong>{summaryCount(summary, "updated")}</strong> update</span>
      <span><strong>{summaryCount(summary, "skipped")}</strong> skip</span>
      <span className={summary.errors?.length ? "has-errors" : ""}><strong>{summary.errors?.length || 0}</strong> issues</span>
    </div>
  ) : null;

  return (
    <Drawer
      title="Training data & forms"
      isOpen={isOpen}
      onClose={onClose}
      closeDisabled={isBusy}
      panelClassName="training-data-centre"
    >
      <div className="training-data-centre__body">
        <section className="training-data-centre__lead">
          <div className="training-data-centre__lead-icon"><FileSpreadsheet size={24} /></div>
          <div>
            <strong>Import, create and export from one place</strong>
            <p>Use the full tracker for controlled migration. Use the smaller imports only when updating one known worksheet.</p>
          </div>
        </section>

        {notice ? <div className="training-data-centre__notice training-data-centre__notice--success"><ShieldCheck size={17} />{notice}</div> : null}
        {error ? <div className="training-data-centre__notice training-data-centre__notice--error">{error}</div> : null}

        <details className="training-data-centre__section" open>
          <summary><span><UploadCloud size={18} /><strong>Import Excel</strong></span><small>Full tracker or targeted worksheets</small></summary>
          <div className="training-data-centre__section-body">
            <button type="button" className="training-data-centre__primary" disabled={!canManage || isBusy} onClick={openFullWorkbook}>
              <FileSpreadsheet size={20} />
              <span><strong>Import complete Training Tracker</strong><small>People, licences, courses, roles, matrix and training history—with preview and conflict review.</small></span>
            </button>

            <div className="training-data-centre__targeted-grid">
              <article className="training-data-centre__import-card">
                <div><BookOpenCheck size={19} /><strong>Course catalogue</strong></div>
                <label className="training-data-centre__file">
                  <FileUp size={17} />
                  <span>{courseFile?.name || "Choose Courses workbook"}</span>
                  <input type="file" accept={acceptedWorkbookTypes} disabled={!canManage || isBusy} onChange={(event) => { setCourseFile(event.target.files?.[0] || null); setCourseSummary(null); }} />
                </label>
                <label>Worksheet<input value={courseSheet} disabled={!canManage || isBusy} onChange={(event) => setCourseSheet(event.target.value)} /></label>
                {renderSummary(courseSummary)}
                <div className="training-data-centre__actions">
                  <button type="button" disabled={!canManage || !courseFile || isBusy} onClick={() => void runTargetedImport("courses", true)}>{busyAction === "courses:preview" ? <Loader2 className="tos-spin" size={15} /> : null} Preview</button>
                  <button type="button" className="primary-chip-btn" disabled={!canManage || !courseFile || !courseSummary || Boolean(courseSummary.errors?.length) || isBusy} onClick={() => void runTargetedImport("courses", false)}>Commit</button>
                </div>
              </article>

              <article className="training-data-centre__import-card">
                <div><GraduationCap size={19} /><strong>Training history</strong></div>
                <label className="training-data-centre__file">
                  <FileUp size={17} />
                  <span>{recordFile?.name || "Choose Training workbook"}</span>
                  <input type="file" accept={acceptedWorkbookTypes} disabled={!canManage || isBusy} onChange={(event) => { setRecordFile(event.target.files?.[0] || null); setRecordSummary(null); }} />
                </label>
                <label>Worksheet<input value={recordSheet} disabled={!canManage || isBusy} onChange={(event) => setRecordSheet(event.target.value)} /></label>
                {renderSummary(recordSummary)}
                <div className="training-data-centre__actions">
                  <button type="button" disabled={!canManage || !recordFile || isBusy} onClick={() => void runTargetedImport("records", true)}>{busyAction === "records:preview" ? <Loader2 className="tos-spin" size={15} /> : null} Preview</button>
                  <button type="button" className="primary-chip-btn" disabled={!canManage || !recordFile || !recordSummary || Boolean(recordSummary.errors?.length) || isBusy} onClick={() => void runTargetedImport("records", false)}>Commit</button>
                </div>
              </article>
            </div>
          </div>
        </details>

        <details className="training-data-centre__section">
          <summary><span><ListPlus size={18} /><strong>Portal forms</strong></span><small>Create governed records without Excel</small></summary>
          <div className="training-data-centre__section-body training-data-centre__form-grid">
            <button type="button" disabled={!canManage || isBusy} onClick={() => openPortalForm(onCreateCourse)}><BookOpenCheck size={18} /><span><strong>New course</strong><small>Add a catalogue item.</small></span></button>
            <button type="button" disabled={!canManage || isBusy} onClick={() => openPortalForm(onCreateRequirement)}><ShieldCheck size={18} /><span><strong>New requirement</strong><small>Add an applicability or release-gate rule.</small></span></button>
            <button type="button" disabled={isBusy} onClick={() => openPortalForm(onOpenGovernanceForms)}><GraduationCap size={18} /><span><strong>Governance forms</strong><small>Experience, effectiveness, competence and remedial actions.</small></span></button>
          </div>
        </details>

        <details className="training-data-centre__section">
          <summary><span><Download size={18} /><strong>Export data</strong></span><small>Download current portal extracts</small></summary>
          <div className="training-data-centre__section-body training-data-centre__actions">
            <button type="button" disabled={isBusy} onClick={onExportCourses}><Download size={16} /> Course catalogue CSV</button>
            <button type="button" disabled={isBusy} onClick={onExportTraining}><Download size={16} /> Training records CSV</button>
          </div>
        </details>

        {issueCount > 0 ? <p className="training-data-centre__footnote">Resolve the reported preview issues before using Commit.</p> : null}
      </div>
    </Drawer>
  );
};

export default TrainingDataCenterDrawer;
