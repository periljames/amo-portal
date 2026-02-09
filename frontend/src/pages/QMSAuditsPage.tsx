import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import AuditHistoryPanel from "../components/QMS/AuditHistoryPanel";
import Drawer from "../components/shared/Drawer";
import EmptyState from "../components/shared/EmptyState";
import InlineError from "../components/shared/InlineError";
import SectionCard from "../components/shared/SectionCard";
import { useToast } from "../components/feedback/ToastProvider";
import { getContext } from "../services/auth";
import { listAdminDepartments, type AdminDepartmentRead } from "../services/adminUsers";
import {
  downloadAuditEvidencePack,
  qmsListAudits,
  qmsListAuditSchedules,
  qmsCreateAuditSchedule,
  qmsRunAuditSchedule,
  qmsRunAuditReminders,
  qmsUploadAuditChecklist,
  qmsDownloadAuditChecklist,
  qmsUploadAuditReport,
  qmsDownloadAuditReport,
  qmsListFindings,
  qmsVerifyFinding,
  qmsCloseFinding,
  qmsAcknowledgeFinding,
  type QMSAuditOut,
  type QMSAuditStatus,
  type QMSAuditScheduleOut,
  type QMSAuditScheduleFrequency,
  type QMSFindingOut,
} from "../services/qms";

type LoadState = "idle" | "loading" | "ready" | "error";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_OPTIONS: Array<{ value: QMSAuditStatus | "ALL"; label: string }> =
  [
    { value: "ALL", label: "All statuses" },
    { value: "PLANNED", label: "Planned" },
    { value: "IN_PROGRESS", label: "In progress" },
    { value: "CAP_OPEN", label: "CAP open" },
    { value: "CLOSED", label: "Closed" },
  ];

const QMSAuditsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);
  const [schedules, setSchedules] = useState<QMSAuditScheduleOut[]>([]);
  const [statusFilter, setStatusFilter] = useState<QMSAuditStatus | "ALL">(
    "ALL"
  );
  const [search, setSearch] = useState("");
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [scheduleState, setScheduleState] = useState<LoadState>("idle");
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [scheduleForm, setScheduleForm] = useState({
    title: "",
    frequency: "MONTHLY" as QMSAuditScheduleFrequency,
    next_due_date: "",
    duration_days: 1,
    auditee: "",
    auditee_email: "",
  });
  const [scheduleDrawerOpen, setScheduleDrawerOpen] = useState(false);
  const [scheduleDepartmentId, setScheduleDepartmentId] = useState("");
  const [departments, setDepartments] = useState<AdminDepartmentRead[]>([]);
  const [departmentsLoading, setDepartmentsLoading] = useState(false);
  const [departmentsError, setDepartmentsError] = useState<string | null>(null);
  const [reminderBusy, setReminderBusy] = useState(false);
  const [runningScheduleId, setRunningScheduleId] = useState<string | null>(null);
  const [uploadingChecklistId, setUploadingChecklistId] = useState<string | null>(null);
  const [uploadingReportId, setUploadingReportId] = useState<string | null>(null);
  const [pendingChecklistAuditId, setPendingChecklistAuditId] = useState<string | null>(null);
  const [pendingReportAuditId, setPendingReportAuditId] = useState<string | null>(null);
  const checklistInputRef = useRef<HTMLInputElement | null>(null);
  const reportInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedAuditId, setSelectedAuditId] = useState<string | null>(null);
  const [findings, setFindings] = useState<QMSFindingOut[]>([]);
  const [findingsState, setFindingsState] = useState<LoadState>("idle");
  const [findingsError, setFindingsError] = useState<string | null>(null);
  const { pushToast } = useToast();

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const data = await qmsListAudits({
        domain: "AMO",
        status_: statusFilter === "ALL" ? undefined : statusFilter,
      });
      setAudits(data);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load audit programme.");
      setState("error");
    }
  };

  const loadSchedules = async () => {
    setScheduleState("loading");
    setScheduleError(null);
    try {
      const data = await qmsListAuditSchedules({ domain: "AMO", active: true });
      setSchedules(data);
      setScheduleState("ready");
    } catch (e: any) {
      setScheduleError(e?.message || "Failed to load audit schedules.");
      setScheduleState("error");
    }
  };

  const loadDepartments = async () => {
    setDepartmentsLoading(true);
    setDepartmentsError(null);
    try {
      const data = await listAdminDepartments();
      setDepartments(data.filter((dept) => dept.is_active));
    } catch (e: any) {
      setDepartmentsError(e?.message || "Failed to load departments.");
    } finally {
      setDepartmentsLoading(false);
    }
  };

  const handleExport = async (audit: QMSAuditOut) => {
    setExportingId(audit.id);
    try {
      const blob = await downloadAuditEvidencePack(audit.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit_${audit.audit_ref}_evidence_pack.zip`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      pushToast({
        title: "Export failed",
        message: e?.message || "Failed to export evidence pack.",
        variant: "error",
      });
    } finally {
      setExportingId(null);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  useEffect(() => {
    loadSchedules();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadDepartments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateSchedule = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!scheduleForm.title.trim() || !scheduleForm.next_due_date) return;
    setScheduleState("loading");
    setScheduleError(null);
    try {
      await qmsCreateAuditSchedule({
        domain: "AMO",
        kind: "INTERNAL",
        frequency: scheduleForm.frequency,
        title: scheduleForm.title.trim(),
        next_due_date: scheduleForm.next_due_date,
        duration_days: Number(scheduleForm.duration_days) || 1,
        auditee: scheduleForm.auditee.trim() || null,
        auditee_email: scheduleForm.auditee_email.trim() || null,
      });
      setScheduleForm((prev) => ({
        ...prev,
        title: "",
        next_due_date: "",
        auditee: "",
        auditee_email: "",
      }));
      setScheduleDepartmentId("");
      setScheduleDrawerOpen(false);
      await loadSchedules();
    } catch (e: any) {
      setScheduleError(e?.message || "Failed to create audit schedule.");
      setScheduleState("error");
    }
  };

  const handleRunSchedule = async (scheduleId: string) => {
    setRunningScheduleId(scheduleId);
    setScheduleError(null);
    try {
      await qmsRunAuditSchedule(scheduleId);
      await Promise.all([load(), loadSchedules()]);
    } catch (e: any) {
      setScheduleError(e?.message || "Failed to generate audit from schedule.");
    } finally {
      setRunningScheduleId(null);
    }
  };

  const handleRunReminders = async () => {
    setReminderBusy(true);
    setScheduleError(null);
    try {
      await qmsRunAuditReminders(7);
    } catch (e: any) {
      setScheduleError(e?.message || "Failed to send audit reminders.");
    } finally {
      setReminderBusy(false);
    }
  };

  const loadFindings = async (auditId: string) => {
    setFindingsState("loading");
    setFindingsError(null);
    try {
      const data = await qmsListFindings(auditId);
      setFindings(data);
      setFindingsState("ready");
    } catch (e: any) {
      setFindingsError(e?.message || "Failed to load findings.");
      setFindingsState("error");
    }
  };

  const handleToggleFindings = (auditId: string) => {
    if (selectedAuditId === auditId) {
      setSelectedAuditId(null);
      setFindings([]);
      setFindingsState("idle");
      return;
    }
    setSelectedAuditId(auditId);
    loadFindings(auditId);
  };

  const handleAcknowledgeFinding = async (finding: QMSFindingOut) => {
    const name = window.prompt("Acknowledged by (name):");
    if (!name) return;
    const email = window.prompt("Acknowledged by (email):");
    if (!email) return;
    setFindingsError(null);
    try {
      await qmsAcknowledgeFinding(finding.id, {
        acknowledged_by_name: name,
        acknowledged_by_email: email,
      });
      if (selectedAuditId) {
        await loadFindings(selectedAuditId);
      }
    } catch (e: any) {
      setFindingsError(e?.message || "Failed to acknowledge finding.");
    }
  };

  const handleVerifyFinding = async (finding: QMSFindingOut) => {
    const evidence = window.prompt("Objective evidence (optional):") || "";
    setFindingsError(null);
    try {
      await qmsVerifyFinding(finding.id, { objective_evidence: evidence || null });
      if (selectedAuditId) {
        await loadFindings(selectedAuditId);
      }
    } catch (e: any) {
      setFindingsError(e?.message || "Failed to verify finding.");
    }
  };

  const handleCloseFinding = async (finding: QMSFindingOut) => {
    if (!window.confirm("Close this finding?")) return;
    setFindingsError(null);
    try {
      await qmsCloseFinding(finding.id);
      if (selectedAuditId) {
        await loadFindings(selectedAuditId);
      }
    } catch (e: any) {
      setFindingsError(e?.message || "Failed to close finding.");
    }
  };

  const handleChecklistUploadClick = (auditId: string) => {
    setPendingChecklistAuditId(auditId);
    checklistInputRef.current?.click();
  };

  const handleReportUploadClick = (auditId: string) => {
    setPendingReportAuditId(auditId);
    reportInputRef.current?.click();
  };

  const handleChecklistFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file || !pendingChecklistAuditId) return;
    setUploadingChecklistId(pendingChecklistAuditId);
    try {
      await qmsUploadAuditChecklist(pendingChecklistAuditId, file);
      await load();
    } catch (e: any) {
      pushToast({
        title: "Upload failed",
        message: e?.message || "Failed to upload checklist.",
        variant: "error",
      });
    } finally {
      setUploadingChecklistId(null);
      setPendingChecklistAuditId(null);
      event.target.value = "";
    }
  };

  const handleReportFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file || !pendingReportAuditId) return;
    setUploadingReportId(pendingReportAuditId);
    try {
      await qmsUploadAuditReport(pendingReportAuditId, file);
      await load();
    } catch (e: any) {
      pushToast({
        title: "Upload failed",
        message: e?.message || "Failed to upload report.",
        variant: "error",
      });
    } finally {
      setUploadingReportId(null);
      setPendingReportAuditId(null);
      event.target.value = "";
    }
  };

  const handleDownloadChecklist = async (audit: QMSAuditOut) => {
    try {
      const blob = await qmsDownloadAuditChecklist(audit.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit_${audit.audit_ref}_checklist`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      pushToast({
        title: "Download failed",
        message: e?.message || "Failed to download checklist.",
        variant: "error",
      });
    }
  };

  const handleDownloadReport = async (audit: QMSAuditOut) => {
    try {
      const blob = await qmsDownloadAuditReport(audit.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit_${audit.audit_ref}_report`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      pushToast({
        title: "Download failed",
        message: e?.message || "Failed to download report.",
        variant: "error",
      });
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return audits;
    return audits.filter(
      (audit) =>
        audit.title.toLowerCase().includes(q) ||
        audit.audit_ref.toLowerCase().includes(q) ||
        audit.kind.toLowerCase().includes(q)
    );
  }, [audits, search]);

  const upcoming = filtered
    .filter((audit) => audit.planned_start && new Date(audit.planned_start) > new Date())
    .sort((a, b) => new Date(a.planned_start || "").getTime() - new Date(b.planned_start || "").getTime())
    .slice(0, 6);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Audits & Inspections"
      subtitle="Plan, execute, and close quality audits with compliance visibility."
      actions={
        <>
          <button
            type="button"
            className="primary-chip-btn"
            onClick={() => setScheduleDrawerOpen(true)}
          >
            Create schedule
          </button>
          <button
            type="button"
            className="secondary-chip-btn"
            onClick={handleRunReminders}
            disabled={reminderBusy}
          >
            {reminderBusy ? "Sending reminders…" : "Send 7-day reminders"}
          </button>
          <button type="button" className="secondary-chip-btn" onClick={load}>
            Refresh audits
          </button>
        </>
      }
    >
      <section className="qms-toolbar">
        <label className="qms-field">
          <span>Status</span>
          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as QMSAuditStatus | "ALL")
            }
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="qms-field qms-field--grow">
          <span>Search</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search audit title, reference, or type"
          />
        </label>
      </section>

      <input
        ref={checklistInputRef}
        type="file"
        style={{ display: "none" }}
        onChange={handleChecklistFileChange}
      />
      <input
        ref={reportInputRef}
        type="file"
        style={{ display: "none" }}
        onChange={handleReportFileChange}
      />

      <Drawer
        title="Create audit schedule"
        isOpen={scheduleDrawerOpen}
        onClose={() => setScheduleDrawerOpen(false)}
      >
        {scheduleError && (
          <InlineError message={scheduleError} onAction={loadSchedules} />
        )}
        <form onSubmit={handleCreateSchedule} className="form-grid">
          <label className="form-control" style={{ gridColumn: "1 / 3" }}>
            <span>Schedule title</span>
            <input
              value={scheduleForm.title}
              onChange={(event) =>
                setScheduleForm((prev) => ({ ...prev, title: event.target.value }))
              }
              placeholder="e.g., Monthly AMO compliance audit"
              required
            />
          </label>

          <label className="form-control">
            <span>Frequency</span>
            <select
              value={scheduleForm.frequency}
              onChange={(event) =>
                setScheduleForm((prev) => ({
                  ...prev,
                  frequency: event.target.value as QMSAuditScheduleFrequency,
                }))
              }
            >
              <option value="MONTHLY">Monthly</option>
              <option value="ANNUAL">Annual</option>
            </select>
          </label>

          <label className="form-control">
            <span>Next due date</span>
            <input
              type="date"
              value={scheduleForm.next_due_date}
              onChange={(event) =>
                setScheduleForm((prev) => ({
                  ...prev,
                  next_due_date: event.target.value,
                }))
              }
              required
            />
          </label>

          <label className="form-control">
            <span>Duration (days)</span>
            <input
              type="number"
              min={1}
              max={90}
              value={scheduleForm.duration_days}
              onChange={(event) =>
                setScheduleForm((prev) => ({
                  ...prev,
                  duration_days: Number(event.target.value),
                }))
              }
            />
          </label>

          <label className="form-control">
            <span>Responsible department</span>
            <select
              value={scheduleDepartmentId}
              onChange={(event) => {
                const deptId = event.target.value;
                setScheduleDepartmentId(deptId);
                const dept = departments.find((entry) => entry.id === deptId);
                setScheduleForm((prev) => ({
                  ...prev,
                  auditee: dept ? dept.name : prev.auditee,
                }));
              }}
              disabled={departmentsLoading}
            >
              <option value="">
                {departmentsLoading ? "Loading departments…" : "Select department"}
              </option>
              {departments.map((dept) => (
                <option key={dept.id} value={dept.id}>
                  {dept.name}
                </option>
              ))}
            </select>
            {departmentsError && (
              <span className="text-muted" style={{ marginTop: 6 }}>
                {departmentsError}
              </span>
            )}
          </label>

          <label className="form-control">
            <span>Auditee / team (optional)</span>
            <input
              value={scheduleForm.auditee}
              onChange={(event) => {
                setScheduleDepartmentId("");
                setScheduleForm((prev) => ({ ...prev, auditee: event.target.value }));
              }}
              placeholder="Department / team"
            />
          </label>

          <label className="form-control">
            <span>Auditee email (optional)</span>
            <input
              type="email"
              value={scheduleForm.auditee_email}
              onChange={(event) =>
                setScheduleForm((prev) => ({ ...prev, auditee_email: event.target.value }))
              }
              placeholder="auditee@example.com"
            />
          </label>

          <div className="form-control" style={{ alignSelf: "end" }}>
            <button
              type="submit"
              className="primary-chip-btn"
              disabled={scheduleState === "loading"}
            >
              {scheduleState === "loading" ? "Saving…" : "Create schedule"}
            </button>
          </div>
        </form>
      </Drawer>

      <section className="qms-grid">
        <SectionCard
          title="Recurring audit schedules"
          subtitle="Create monthly or annual audit schedules and generate the next audit instantly."
        >
          {scheduleError && (
            <InlineError message={scheduleError} onAction={loadSchedules} />
          )}
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Frequency</th>
                  <th>Next due</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {scheduleState === "loading" && (
                  <tr>
                    <td colSpan={4} className="text-muted">
                      Loading schedules…
                    </td>
                  </tr>
                )}
                {scheduleState === "ready" &&
                  schedules.map((schedule) => (
                    <tr key={schedule.id}>
                      <td>
                        <strong>{schedule.title}</strong>
                        <div className="text-muted">{schedule.auditee || "No auditee set"}</div>
                      </td>
                      <td>{schedule.frequency}</td>
                      <td>{formatDate(schedule.next_due_date)}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => handleRunSchedule(schedule.id)}
                          disabled={runningScheduleId === schedule.id}
                        >
                          {runningScheduleId === schedule.id ? "Generating…" : "Generate audit"}
                        </button>
                      </td>
                    </tr>
                  ))}
                {scheduleState === "ready" && schedules.length === 0 && (
                  <tr>
                    <td colSpan={4} className="text-muted">
                      No recurring schedules yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </section>

      <section className="qms-grid">
        <SectionCard
          title="Next up"
          subtitle="Immediate audit plan for the coming weeks."
        >
          <div className="qms-list">
            {upcoming.map((audit) => (
              <div key={audit.id} className="qms-list__item">
                <div>
                  <strong>{audit.title}</strong>
                  <span className="qms-list__meta">
                    {audit.audit_ref} · {audit.kind}
                  </span>
                </div>
                <span className="qms-pill qms-pill--info">
                  {formatDate(audit.planned_start)}
                </span>
              </div>
            ))}
            {upcoming.length === 0 && (
              <EmptyState
                title="No upcoming audits"
                description="Create a schedule to populate the upcoming plan."
                action={
                  <button
                    type="button"
                    className="secondary-chip-btn"
                    onClick={() => setScheduleDrawerOpen(true)}
                  >
                    Create schedule
                  </button>
                }
              />
            )}
          </div>
        </SectionCard>

        <SectionCard title="Audit programme">
          {state === "loading" && (
            <p className="text-muted">Loading audits…</p>
          )}
          {state === "error" && (
            <InlineError message={error || "Failed to load audits."} onAction={load} />
          )}
          {state === "ready" && (
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Audit</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Start</th>
                    <th>End</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((audit) => (
                    <tr key={audit.id}>
                      <td>
                        <strong>{audit.title}</strong>
                        <div className="text-muted">{audit.audit_ref}</div>
                      </td>
                      <td>{audit.kind}</td>
                      <td>
                        <span className="qms-pill">{audit.status}</span>
                      </td>
                      <td>{formatDate(audit.planned_start)}</td>
                      <td>{formatDate(audit.planned_end)}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => handleExport(audit)}
                          disabled={exportingId === audit.id}
                        >
                          {exportingId === audit.id ? "Exporting…" : "Export evidence pack"}
                        </button>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => handleChecklistUploadClick(audit.id)}
                          disabled={uploadingChecklistId === audit.id}
                        >
                          {uploadingChecklistId === audit.id ? "Uploading checklist…" : "Upload checklist"}
                        </button>
                        {audit.checklist_file_ref && (
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleDownloadChecklist(audit)}
                          >
                            Download checklist
                          </button>
                        )}
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => handleReportUploadClick(audit.id)}
                          disabled={uploadingReportId === audit.id}
                        >
                          {uploadingReportId === audit.id ? "Uploading report…" : "Upload report"}
                        </button>
                        {audit.report_file_ref && (
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleDownloadReport(audit)}
                          >
                            Download report
                          </button>
                        )}
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={() => handleToggleFindings(audit.id)}
                        >
                          {selectedAuditId === audit.id ? "Hide findings" : "View findings"}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <EmptyState
                          title="No audits found"
                          description="Adjust filters or create a new schedule."
                          action={
                            <button
                              type="button"
                              className="secondary-chip-btn"
                              onClick={() => setScheduleDrawerOpen(true)}
                            >
                              Create schedule
                            </button>
                          }
                        />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </section>

      {selectedAuditId && (
        <section className="page-section">
          <div className="card">
            <div className="card-header">
              <h3>Audit findings</h3>
              <p className="text-muted">
                Review, acknowledge, verify, and close findings for the selected audit.
              </p>
            </div>
            {findingsState === "loading" && <p>Loading findings…</p>}
            {findingsError && (
              <InlineError
                message={findingsError}
                onAction={selectedAuditId ? () => loadFindings(selectedAuditId) : undefined}
              />
            )}
            {findingsState === "ready" && findings.length === 0 && (
              <p className="text-muted">No findings recorded for this audit yet.</p>
            )}
            {findingsState === "ready" && findings.length > 0 && (
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Finding</th>
                      <th>Severity</th>
                      <th>Target close</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((finding) => (
                      <tr key={finding.id}>
                        <td>
                          <strong>{finding.finding_ref || "Finding"}</strong>
                          <div className="text-muted">{finding.description}</div>
                        </td>
                        <td>{finding.severity}</td>
                        <td>{formatDate(finding.target_close_date)}</td>
                        <td>
                          {finding.closed_at ? "Closed" : "Open"}
                          {finding.acknowledged_at && (
                            <div className="text-muted">
                              Acknowledged {formatDate(finding.acknowledged_at)}
                            </div>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleAcknowledgeFinding(finding)}
                            disabled={Boolean(finding.acknowledged_at)}
                          >
                            {finding.acknowledged_at ? "Acknowledged" : "Acknowledge"}
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleVerifyFinding(finding)}
                          >
                            Verify
                          </button>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleCloseFinding(finding)}
                            disabled={Boolean(finding.closed_at)}
                          >
                            {finding.closed_at ? "Closed" : "Close"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="qms-grid">
        <AuditHistoryPanel title="Audit programme history" entityType="qms_audit" />
      </section>
    </QMSLayout>
  );
};

export default QMSAuditsPage;
