import React, { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, RefreshCw, ScanLine } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import Drawer from "../components/shared/Drawer";
import { useToast } from "../components/feedback/ToastProvider";
import { getCachedUser } from "../services/auth";
import { listAdminUserSummaries } from "../services/adminUsers";
import {
  createTrainingCourse,
  getBulkTrainingStatusForUsers,
  importTrainingCoursesWorkbook,
  issueTrainingCertificate,
  listTrainingCertificates,
  listTrainingCourses,
  listTrainingDeferrals,
  listTrainingEventParticipants,
  listTrainingEvents,
  listTrainingRecords,
  listTrainingRequirements,
  updateTrainingCourse,
  type TransferProgress,
  updateTrainingEventParticipant,
} from "../services/training";
import type {
  TrainingCourseRead,
  TrainingDeferralRequestRead,
  TrainingEventRead,
  TrainingRecordRead,
  TrainingStatusItem,
} from "../types/training";
import { shouldUseMockData } from "../services/runtimeMode";

type SectionKey =
  | "overview"
  | "matrix"
  | "schedule"
  | "sessions"
  | "attendance"
  | "assessments"
  | "certificates"
  | "personnel"
  | "templates"
  | "settings";

const sectionItems: Array<{ key: SectionKey; title: string; desc: string }> = [
  { key: "overview", title: "Overview", desc: "Compliance and exceptions" },
  { key: "matrix", title: "Training Matrix", desc: "Role and course requirements" },
  { key: "schedule", title: "Schedule", desc: "Planned sessions" },
  { key: "sessions", title: "Sessions", desc: "Roster and delivery status" },
  { key: "attendance", title: "Attendance", desc: "Sign-in and closeout" },
  { key: "assessments", title: "Assessments", desc: "Exam and outcomes" },
  { key: "certificates", title: "Certificates", desc: "Issued and verification" },
  { key: "personnel", title: "Personnel Records", desc: "Per-person history" },
  { key: "templates", title: "Templates", desc: "Certificate templates" },
  { key: "settings", title: "Admin / Settings", desc: "Policy defaults" },
];

const sampleCourses: TrainingCourseRead[] = [
  {
    id: "sample-course-1",
    amo_id: "sample",
    course_id: "HF-REF",
    course_name: "Sample Human Factors Refresher",
    frequency_months: 12,
    is_mandatory: true,
    mandatory_for_all: false,
    is_active: true,
    created_by_user_id: null,
    updated_by_user_id: null,
  },
];

const sampleEvents: TrainingEventRead[] = [
  {
    id: "sample-event-1",
    amo_id: "sample",
    course_id: "sample-course-1",
    title: "Sample HF Session",
    location: "Training Room",
    provider: "Internal",
    starts_on: "2026-03-20",
    ends_on: null,
    status: "PLANNED",
    notes: "Sample",
    created_by_user_id: null,
  },
];

const sampleRecords: TrainingRecordRead[] = [
  {
    id: "sample-record-1",
    amo_id: "sample",
    user_id: "sample-user",
    course_id: "sample-course-1",
    event_id: "sample-event-1",
    completion_date: "2026-03-01",
    valid_until: "2027-03-01",
    hours_completed: 4,
    exam_score: 87,
    certificate_reference: "SAMPLE-CERT-0001",
    remarks: "Sample",
    is_manual_entry: false,
    created_by_user_id: null,
  },
];

const TrainingCompetencePage: React.FC = () => {
  const { amoCode, department } = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const sectionParam = (searchParams.get("section") || "overview") as SectionKey;

  const [section, setSection] = useState<SectionKey>(sectionParam);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSampleMode, setIsSampleMode] = useState(false);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [records, setRecords] = useState<TrainingRecordRead[]>([]);
  const [certificates, setCertificates] = useState<TrainingRecordRead[]>([]);
  const [deferrals, setDeferrals] = useState<TrainingDeferralRequestRead[]>([]);
  const [statusRows, setStatusRows] = useState<TrainingStatusItem[]>([]);
  const [requirementsCount, setRequirementsCount] = useState(0);
  const [drawer, setDrawer] = useState<{ title: string; body: React.ReactNode } | null>(null);
  const { pushToast } = useToast();
  const currentUser = getCachedUser();
  const canManageCourses = Boolean(
    currentUser?.is_superuser || currentUser?.is_amo_admin || currentUser?.role === "QUALITY_MANAGER"
  );
  const [courseFormOpen, setCourseFormOpen] = useState(false);
  const [editingCourseId, setEditingCourseId] = useState<string | null>(null);
  const [savingCourse, setSavingCourse] = useState(false);
  const [courseForm, setCourseForm] = useState({
    course_id: "",
    course_name: "",
    frequency_months: "",
    status: "One_Off",
    category_raw: "",
    is_mandatory: false,
    scope: "",
    regulatory_reference: "",
  });
  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importDryRun, setImportDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<TransferProgress | null>(null);
  const [importSummary, setImportSummary] = useState<any | null>(null);

  useEffect(() => {
    if (sectionParam !== section) setSection(sectionParam);
  }, [sectionParam, section]);

  const openSection = (next: SectionKey) => {
    setSection(next);
    const sp = new URLSearchParams(searchParams);
    sp.set("section", next);
    setSearchParams(sp, { replace: true });
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [users, nextCourses, nextEvents, nextRecords, nextDeferrals, reqs, certs] = await Promise.all([
        listAdminUserSummaries({ limit: 50 }),
        listTrainingCourses(),
        listTrainingEvents(),
        listTrainingRecords(),
        listTrainingDeferrals({ limit: 50 }),
        listTrainingRequirements(),
        listTrainingCertificates(),
      ]);

      const statusMap = await getBulkTrainingStatusForUsers(users.map((u) => u.id));
      const flattened: TrainingStatusItem[] = Object.values(statusMap.users).flat();

      setIsSampleMode(false);
      setCourses(nextCourses);
      setEvents(nextEvents);
      setRecords(nextRecords);
      setDeferrals(nextDeferrals);
      setStatusRows(flattened);
      setRequirementsCount(reqs.length);
      setCertificates(certs.filter((c) => !String(c.certificate_reference || "").startsWith("TC-DEMO")));
    } catch {
      if (shouldUseMockData()) {
        setIsSampleMode(true);
        setError("Sample data");
        setCourses(sampleCourses);
        setEvents(sampleEvents);
        setRecords(sampleRecords);
        setCertificates(sampleRecords.filter((r) => Boolean(r.certificate_reference)));
        setDeferrals([]);
        setStatusRows([]);
        setRequirementsCount(1);
      } else {
        setIsSampleMode(false);
        setError("Training service unavailable.");
        setCourses([]);
        setEvents([]);
        setRecords([]);
        setCertificates([]);
        setDeferrals([]);
        setStatusRows([]);
        setRequirementsCount(0);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreateCourse = () => {
    setEditingCourseId(null);
    setCourseForm({
      course_id: "",
      course_name: "",
      frequency_months: "",
      status: "One_Off",
      category_raw: "",
      is_mandatory: false,
      scope: "",
      regulatory_reference: "",
    });
    setCourseFormOpen(true);
  };

  const openEditCourse = (course: TrainingCourseRead) => {
    setEditingCourseId(course.id);
    setCourseForm({
      course_id: course.course_id || "",
      course_name: course.course_name || "",
      frequency_months:
        course.frequency_months == null || Number.isNaN(course.frequency_months)
          ? ""
          : String(course.frequency_months),
      status: (course.status || "One_Off") as string,
      category_raw: (course.category_raw || "") as string,
      is_mandatory: Boolean(course.is_mandatory),
      scope: (course.scope || "") as string,
      regulatory_reference: (course.regulatory_reference || "") as string,
    });
    setCourseFormOpen(true);
  };

  const submitCourse = async () => {
    if (!courseForm.course_id.trim() || !courseForm.course_name.trim()) {
      pushToast({ title: "Missing fields", message: "Course ID and Course Name are required.", variant: "error" });
      return;
    }
    setSavingCourse(true);
    try {
      const payload = {
        course_id: courseForm.course_id.trim(),
        course_name: courseForm.course_name.trim(),
        frequency_months: courseForm.frequency_months.trim() ? Number(courseForm.frequency_months.trim()) : null,
        status: courseForm.status,
        category_raw: courseForm.category_raw.trim() || null,
        scope: courseForm.scope.trim() || null,
        regulatory_reference: courseForm.regulatory_reference.trim() || null,
        is_mandatory: courseForm.is_mandatory,
        mandatory_for_all: false,
      };
      if (editingCourseId) {
        await updateTrainingCourse(editingCourseId, payload);
        pushToast({ title: "Course updated", message: `${payload.course_id} updated successfully.`, variant: "info" });
      } else {
        await createTrainingCourse(payload);
        pushToast({ title: "Course created", message: `${payload.course_id} created successfully.`, variant: "info" });
      }
      setCourseFormOpen(false);
      await load();
    } catch (e: any) {
      pushToast({ title: "Save failed", message: e?.message || "Unable to save course.", variant: "error" });
    } finally {
      setSavingCourse(false);
    }
  };

  const runImport = async () => {
    if (!importFile) {
      pushToast({ title: "No file selected", message: "Choose a COURSES.xlsx file first.", variant: "error" });
      return;
    }
    setImporting(true);
    setImportProgress(null);
    setImportSummary(null);
    try {
      const summary = await importTrainingCoursesWorkbook(importFile, {
        dryRun: importDryRun,
        sheetName: "Courses",
        onProgress: setImportProgress,
      });
      setImportSummary(summary);
      pushToast({
        title: importDryRun ? "Dry-run completed" : "Import completed",
        message: `${summary.created_courses} created, ${summary.updated_courses} updated, ${summary.skipped_rows} skipped.`,
        variant: "info",
      });
      if (!importDryRun) await load();
    } catch (e: any) {
      pushToast({ title: "Import failed", message: e?.message || "Could not import courses.", variant: "error" });
    } finally {
      setImporting(false);
    }
  };

  const summary = useMemo(
    () => ({
      overdue: statusRows.filter((x) => x.status === "OVERDUE").length,
      dueSoon: statusRows.filter((x) => x.status === "DUE_SOON").length,
      initialRequired: statusRows.filter((x) => x.status === "NOT_DONE").length,
      deferralsPending: deferrals.filter((x) => x.status === "PENDING").length,
      attendancePending: events.filter((x) => x.status === "IN_PROGRESS").length,
    }),
    [deferrals, events, statusRows],
  );

  const sectionCount = (key: SectionKey): number | null => {
    if (key === "overview") return statusRows.length;
    if (key === "matrix") return requirementsCount;
    if (key === "schedule" || key === "sessions") return events.length;
    if (key === "attendance") return summary.attendancePending;
    if (key === "assessments") return records.filter((x) => x.exam_score == null).length;
    if (key === "certificates") return certificates.length;
    if (key === "personnel") return records.length;
    return null;
  };

  return (
    <QMSLayout
      amoCode={amoCode || "UNKNOWN"}
      department={department || "quality"}
      title="Training & Competence"
      subtitle="Operational training lifecycle"
      actions={
        <button
          type="button"
          className="secondary-chip-btn"
          aria-label="Refresh training module"
          title="Refresh"
          onClick={load}
        >
          <RefreshCw size={14} />
        </button>
      }
    >
      <div style={{ maxWidth: 1120, margin: "0 auto", width: "100%" }}>
        <section className="card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>Module Sections</h3>
          {isSampleMode ? <p className="text-muted" style={{ margin: "0 0 10px" }}>Sample data</p> : null}
          {!isSampleMode && error ? <p className="text-muted" style={{ margin: "0 0 10px" }}>{error}</p> : null}
          <div style={{ display: "grid", gap: 8 }}>
            {sectionItems.map((item) => (
              <div
                key={item.key}
                role="button"
                tabIndex={0}
                onClick={() => openSection(item.key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") openSection(item.key);
                }}
                style={{
                  border: `1px solid ${item.key === section ? "var(--accent,#3b82f6)" : "var(--line,#d0d7de)"}`,
                  borderRadius: 10,
                  padding: 12,
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                  alignItems: "center",
                  cursor: "pointer",
                }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{item.title}</div>
                  <div className="text-muted" style={{ fontSize: 13 }}>{item.desc}</div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {sectionCount(item.key) != null ? <span className="badge">{sectionCount(item.key)}</span> : null}
                  <span aria-hidden>›</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {loading ? (
          <section className="card">
            <p className="text-muted">Loading training module…</p>
          </section>
        ) : (
          <SectionContent
            section={section}
            summary={summary}
            courses={courses}
            requirementsCount={requirementsCount}
            events={events}
            records={records}
            certificates={certificates}
            deferrals={deferrals}
            canManageCourses={canManageCourses}
            onOpenCreateCourse={openCreateCourse}
            onOpenEditCourse={openEditCourse}
            onOpenImportCourses={() => setImportOpen(true)}
            load={load}
            setDrawer={setDrawer}
            navigate={navigate}
            amoCode={amoCode}
            department={department}
            isSampleMode={isSampleMode}
          />
        )}
      </div>

      <Drawer title={drawer?.title || "Details"} isOpen={Boolean(drawer)} onClose={() => setDrawer(null)}>
        <div style={{ padding: 16 }}>{drawer?.body}</div>
      </Drawer>

      <Drawer
        title={editingCourseId ? "Modify course" : "Create course"}
        isOpen={courseFormOpen}
        onClose={() => setCourseFormOpen(false)}
      >
        <div style={{ padding: 16, display: "grid", gap: 10 }}>
          <input className="input" placeholder="Course ID" value={courseForm.course_id} onChange={(e) => setCourseForm((p) => ({ ...p, course_id: e.target.value }))} />
          <input className="input" placeholder="Course name" value={courseForm.course_name} onChange={(e) => setCourseForm((p) => ({ ...p, course_name: e.target.value }))} />
          <input className="input" placeholder="Frequency months (blank allowed)" value={courseForm.frequency_months} onChange={(e) => setCourseForm((p) => ({ ...p, frequency_months: e.target.value }))} />
          <select className="input" value={courseForm.status} onChange={(e) => setCourseForm((p) => ({ ...p, status: e.target.value }))}>
            <option value="Initial">Initial</option>
            <option value="Recurrent">Recurrent</option>
            <option value="One_Off">One_Off</option>
          </select>
          <input className="input" placeholder="Category (raw)" value={courseForm.category_raw} onChange={(e) => setCourseForm((p) => ({ ...p, category_raw: e.target.value }))} />
          <input className="input" placeholder="Scope (e.g. All Staff)" value={courseForm.scope} onChange={(e) => setCourseForm((p) => ({ ...p, scope: e.target.value }))} />
          <input className="input" placeholder="Reference" value={courseForm.regulatory_reference} onChange={(e) => setCourseForm((p) => ({ ...p, regulatory_reference: e.target.value }))} />
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={courseForm.is_mandatory} onChange={(e) => setCourseForm((p) => ({ ...p, is_mandatory: e.target.checked }))} />
            Mandatory
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="secondary-chip-btn" onClick={() => setCourseFormOpen(false)} disabled={savingCourse}>Cancel</button>
            <button type="button" className="secondary-chip-btn" onClick={submitCourse} disabled={savingCourse}>
              {savingCourse ? "Saving…" : editingCourseId ? "Update course" : "Create course"}
            </button>
          </div>
        </div>
      </Drawer>

      <Drawer title="Import courses workbook" isOpen={importOpen} onClose={() => setImportOpen(false)}>
        <div style={{ padding: 16, display: "grid", gap: 10 }}>
          <input type="file" accept=".xlsx,.xlsm,.xltx,.xltm" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={importDryRun} onChange={(e) => setImportDryRun(e.target.checked)} />
            Dry-run only
          </label>
          {importProgress?.percent != null ? <p className="text-muted" style={{ margin: 0 }}>Uploading… {importProgress.percent.toFixed(1)}%</p> : null}
          <button type="button" className="secondary-chip-btn" onClick={runImport} disabled={importing}>
            {importing ? "Processing…" : importDryRun ? "Run dry-run import" : "Run live import"}
          </button>
          {importSummary ? (
            <p className="text-muted" style={{ margin: 0 }}>
              Rows: {importSummary.total_rows} · Created: {importSummary.created_courses} · Updated: {importSummary.updated_courses} · Skipped: {importSummary.skipped_rows}
            </p>
          ) : null}
        </div>
      </Drawer>
    </QMSLayout>
  );
};

type SectionContentProps = {
  section: SectionKey;
  summary: { overdue: number; dueSoon: number; initialRequired: number; deferralsPending: number; attendancePending: number };
  courses: TrainingCourseRead[];
  requirementsCount: number;
  events: TrainingEventRead[];
  records: TrainingRecordRead[];
  certificates: TrainingRecordRead[];
  deferrals: TrainingDeferralRequestRead[];
  canManageCourses: boolean;
  onOpenCreateCourse: () => void;
  onOpenEditCourse: (course: TrainingCourseRead) => void;
  onOpenImportCourses: () => void;
  load: () => Promise<void>;
  setDrawer: (d: { title: string; body: React.ReactNode } | null) => void;
  navigate: ReturnType<typeof useNavigate>;
  amoCode?: string;
  department?: string;
  isSampleMode: boolean;
};

const SectionContent: React.FC<SectionContentProps> = ({
  section,
  summary,
  courses,
  requirementsCount,
  events,
  records,
  certificates,
  deferrals,
  canManageCourses,
  onOpenCreateCourse,
  onOpenEditCourse,
  onOpenImportCourses,
  load,
  setDrawer,
  navigate,
  amoCode,
  department,
  isSampleMode,
}) => {
  if (section === "overview") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Overview</h3>
        <div className="kpi-grid">
          <button type="button" className="secondary-chip-btn" onClick={() => setDrawer({ title: "Due soon", body: <p>{summary.dueSoon} due soon.</p> })}>Due soon: {summary.dueSoon}</button>
          <button type="button" className="secondary-chip-btn" onClick={() => setDrawer({ title: "Overdue", body: <p>{summary.overdue} overdue.</p> })}>Overdue: {summary.overdue}</button>
          <button type="button" className="secondary-chip-btn" onClick={() => setDrawer({ title: "Initial", body: <p>{summary.initialRequired} initial required.</p> })}>Initial: {summary.initialRequired}</button>
          <button type="button" className="secondary-chip-btn" onClick={() => setDrawer({ title: "Deferrals", body: <p>{summary.deferralsPending} pending.</p> })}>Deferrals: {summary.deferralsPending}</button>
        </div>
      </section>
    );
  }

  if (section === "matrix") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Training Matrix</h3>
        <p className="text-muted">Courses: {courses.length} · Requirements: {requirementsCount}</p>
        {canManageCourses ? (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <button type="button" className="secondary-chip-btn" onClick={onOpenCreateCourse}>
              + New course
            </button>
            <button type="button" className="secondary-chip-btn" onClick={onOpenImportCourses}>
              Import COURSES.xlsx
            </button>
          </div>
        ) : null}
        {canManageCourses && courses.length > 0 ? (
          <div style={{ display: "grid", gap: 6, marginBottom: 10 }}>
            {courses.slice(0, 12).map((course) => (
              <div key={course.id} style={{ display: "flex", justifyContent: "space-between", gap: 10, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                <span>{course.course_id} · {course.course_name}</span>
                <button type="button" className="secondary-chip-btn" onClick={() => onOpenEditCourse(course)}>
                  Modify
                </button>
              </div>
            ))}
          </div>
        ) : null}
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/training`)}>
          Open matrix
        </button>
      </section>
    );
  }

  if (section === "schedule" || section === "sessions") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>{section === "schedule" ? "Schedule" : "Sessions"}</h3>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/events`)}>
          Open schedule
        </button>
      </section>
    );
  }

  if (section === "attendance") return <AttendancePanel events={events} setDrawer={setDrawer} />;

  if (section === "assessments") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Assessments</h3>
        <p className="text-muted">Pending: {records.filter((r) => r.exam_score == null).length}</p>
      </section>
    );
  }

  if (section === "certificates") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Certificates</h3>
        {certificates.length === 0 ? (
          <p className="text-muted">No certificates yet.</p>
        ) : (
          <ul className="list-unstyled" style={{ margin: 0, padding: 0 }}>
            {certificates.slice(0, 20).map((record) => (
              <li
                key={record.id}
                style={{ borderTop: "1px solid var(--line)", padding: "10px 0", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}
              >
                <span style={{ fontWeight: 600 }}>{record.certificate_reference || "Not issued"}</span>
                {!record.certificate_reference ? (
                  <button
                    type="button"
                    className="secondary-chip-btn"
                    onClick={async () => {
                      await issueTrainingCertificate(record.id);
                      await load();
                    }}
                    disabled={isSampleMode}
                    title={isSampleMode ? "Unavailable in sample mode" : "Issue certificate"}
                  >
                    Issue
                  </button>
                ) : (
                  <button
                    type="button"
                    className="secondary-chip-btn"
                    onClick={() =>
                      setDrawer({
                        title: "Certificate detail",
                        body: (
                          <div>
                            <p style={{ marginTop: 0, overflowWrap: "anywhere" }}><strong>Certificate:</strong> {record.certificate_reference}</p>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              <button
                                type="button"
                                className="secondary-chip-btn"
                                aria-label="Download certificate"
                                title="Download unavailable until certificate artifact is stored"
                                disabled
                              >
                                <Download size={14} />
                              </button>
                              <button
                                type="button"
                                className="secondary-chip-btn"
                                aria-label="Scan certificate"
                                title="Scan"
                                onClick={() => window.open("/verify/scan", "_blank")}
                              >
                                <ScanLine size={14} />
                              </button>
                              <button
                                type="button"
                                className="secondary-chip-btn"
                                aria-label="Open verify page"
                                title="Open verify page"
                                onClick={() => window.open(`/verify/certificate/${record.certificate_reference}`, "_blank")}
                              >
                                <ExternalLink size={14} />
                              </button>
                            </div>
                          </div>
                        ),
                      })
                    }
                  >
                    View
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  if (section === "personnel") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Personnel Records</h3>
        <p>Total records: {records.length}</p>
        <p>Total deferrals: {deferrals.length}</p>
      </section>
    );
  }

  if (section === "templates") {
    return (
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Templates</h3>
        <p className="text-muted">Controlled template/version management.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h3 style={{ marginTop: 0 }}>Admin / Settings</h3>
      <p className="text-muted">Intervals and numbering rules.</p>
    </section>
  );
};

const AttendancePanel: React.FC<{ events: TrainingEventRead[]; setDrawer: (d: { title: string; body: React.ReactNode } | null) => void }> = ({ events, setDrawer }) => {
  const [selectedEvent, setSelectedEvent] = useState<string>("");
  const [participants, setParticipants] = useState<any[]>([]);

  useEffect(() => {
    if (!selectedEvent) return;
    listTrainingEventParticipants(selectedEvent).then(setParticipants).catch(() => setParticipants([]));
  }, [selectedEvent]);

  return (
    <section className="card">
      <h3 style={{ marginTop: 0 }}>Attendance</h3>
      <select value={selectedEvent} onChange={(e) => setSelectedEvent(e.target.value)}>
        <option value="">Select session</option>
        {events.map((event) => (
          <option key={event.id} value={event.id}>
            {event.title} ({event.starts_on})
          </option>
        ))}
      </select>
      <ul className="list-unstyled" style={{ marginTop: 10, padding: 0 }}>
        {participants.map((p) => (
          <li key={p.id} style={{ borderTop: "1px solid var(--line)", padding: "10px 0", display: "flex", flexWrap: "wrap", gap: 8 }}>
            <span>{p.user_id?.slice?.(0, 8) || "user"} · {p.status}</span>
            <button
              type="button"
              className="secondary-chip-btn"
              onClick={async () => {
                await updateTrainingEventParticipant(p.id, { status: "ATTENDED" });
                setDrawer({ title: "Attendance updated", body: <p>Marked participant as ATTENDED.</p> });
              }}
            >
              Mark attended
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default TrainingCompetencePage;
