import { AlertCircle, CheckCircle2, Download, Eye, FilePlus2, FileText, History, MoreHorizontal, Pencil, Search, ShieldCheck, Trash2 } from "lucide-react";
import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import type { TrainingFileRead } from "../../services/training";
import type { TrainingCourseRead, TrainingRecordRead, TrainingStatusItem } from "../../types/training";
import { canonicalTrainingType, complianceStatusLabel, explicitTrainingRequirementKey, isNonRecurrentInitial, trainingTypeLabel } from "../../utils/trainingPresentation";
import { filesByIdMap, latestEvidenceByRecord, resolveRecordEvidence } from "./trainingRequirementEvidence";
import "./TrainingRequirementList.css";

type Props = {
  items: TrainingStatusItem[];
  courses: TrainingCourseRead[];
  records: TrainingRecordRead[];
  files: TrainingFileRead[];
  canEdit: boolean;
  busy?: boolean;
  initialFilter?: string;
  onEditRecord?: (record: TrainingRecordRead) => void;
  onDeleteRecord?: (record: TrainingRecordRead) => void;
  onOpenEvidence?: (file: TrainingFileRead) => void;
  onDownloadEvidence?: (file: TrainingFileRead) => void;
  onUploadEvidence?: (recordId: string) => void;
  onRecordCompletion?: (coursePk: string) => void;
};
export type RequirementRow = {
  key: string;
  mandatory: boolean;
  item: TrainingStatusItem;
  course: TrainingCourseRead | null;
  courses: TrainingCourseRead[];
  latestRecord: TrainingRecordRead | null;
  history: TrainingRecordRead[];
  evidence: TrainingFileRead | null;
  status: string;
};
function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value.includes("T") ? value : `${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}
function dueDate(item: TrainingStatusItem): string | null { return item.extended_due_date || item.valid_until || null; }
function recordTime(record: TrainingRecordRead): number { return Date.parse(record.completion_date || record.created_at || "") || 0; }
function isHistorical(record: TrainingRecordRead): boolean {
  return ["RENEWED", "SUPERSEDED", "INACTIVE"].includes(String(record.record_status || record.source_status || "ACTIVE").trim().toUpperCase());
}
function byCourseForHistory(courses: TrainingCourseRead[], record: TrainingRecordRead): TrainingCourseRead | null {
  return courses.find((course) => [course.id, course.course_pk, course.course_id].filter(Boolean).some((id) => id === record.course_pk || id === record.course_id)) || null;
}
/* eslint-disable-next-line react-refresh/only-export-components -- deterministic requirement projection exported for tests. */
export function buildRows(
  items: TrainingStatusItem[],
  courses: TrainingCourseRead[],
  records: TrainingRecordRead[],
  files: TrainingFileRead[],
): RequirementRow[] {
  const byCourse = new Map<string, TrainingCourseRead>();
  courses.forEach((course) => {
    if (course.course_pk) byCourse.set(String(course.course_pk), course);
    if (course.id) byCourse.set(String(course.id), course);
    if (course.course_id) byCourse.set(String(course.course_id), course);
  });

  const asPresentation = (course: TrainingCourseRead | null, item?: TrainingStatusItem) => {
    if (course) return course;
    if (!item) return null;
    return {
      id: item.course_pk || item.course_id,
      course_pk: item.course_pk,
      course_id: item.course_id,
      course_name: item.course_name,
      kind: item.kind,
      group_code: item.group_code,
      prerequisite_course_id: item.prerequisite_course_id,
      is_mandatory: item.is_mandatory,
      frequency_months: item.frequency_months,
    } as TrainingCourseRead;
  };

  const requirementKey = (course: TrainingCourseRead | null): string => {
    if (!course) return "unknown";
    return explicitTrainingRequirementKey(course, courses) || `course:${course.id || course.course_id || "unknown"}`;
  };

  const grouped = new Map<string, Array<{ item: TrainingStatusItem; course: TrainingCourseRead | null }>>();
  items.forEach((item) => {
    const resolved = byCourse.get(String(item.course_pk || ""))
      || byCourse.get(String(item.course_id))
      || courses.find((candidate) => candidate.course_name === item.course_name)
      || null;
    const forKey = resolved || asPresentation(null, item);
    const key = requirementKey(forKey);
    const list = grouped.get(key) || [];
    list.push({ item, course: resolved || (forKey as TrainingCourseRead) });
    grouped.set(key, list);
  });

  const latestFileByRecord = latestEvidenceByRecord(files);
  const filesById = filesByIdMap(files);

  const rows: RequirementRow[] = [];
  grouped.forEach((members, key) => {
    const selected = members.slice().sort((a, b) => {
      const rank = (value: typeof a) => canonicalTrainingType(value.course || asPresentation(null, value.item)) === "RECURRENT" ? 2 : canonicalTrainingType(value.course || asPresentation(null, value.item)) === "INITIAL" ? 1 : 0;
      return rank(b) - rank(a);
    })[0];
    const selectedCourse = selected.course || asPresentation(null, selected.item);
    const groupCourses = courses.filter((course) => requirementKey(course) === key);
    const ids = new Set<string>();
    groupCourses.forEach((course) => { if (course.course_pk) ids.add(String(course.course_pk)); if (course.id) ids.add(String(course.id)); if (course.course_id) ids.add(String(course.course_id)); });
    members.forEach(({ item, course }) => {
      ids.add(String(item.course_id));
      if (item.course_pk) ids.add(String(item.course_pk));
      if (course?.id) ids.add(String(course.id));
      if (course?.course_pk) ids.add(String(course.course_pk));
      if (course?.course_id) ids.add(String(course.course_id));
    });
    const history = records.filter((record) => ids.has(String(record.course_id)) || ids.has(String(record.course_pk || ""))).sort((a, b) => recordTime(b) - recordTime(a));
    const selectedIds = new Set([selectedCourse?.id, selectedCourse?.course_id, selectedCourse?.course_pk, selected.item.course_pk, selected.item.course_id].filter(Boolean).map(String));
    history.sort((a, b) => recordTime(b) - recordTime(a) || Number(selectedIds.has(String(b.course_pk || "")) || selectedIds.has(String(b.course_id))) - Number(selectedIds.has(String(a.course_pk || "")) || selectedIds.has(String(a.course_id))));
    const latestRecord = history.find((record) => !isHistorical(record)) || history[0] || null;
    let status = complianceStatusLabel(selected.item.status);
    if (status === "Current" && isNonRecurrentInitial(selectedCourse)) status = "Completed";
    rows.push({
      mandatory: members.some(({ item, course }) => item.is_mandatory ?? course?.is_mandatory ?? course?.mandatory_for_all ?? true),
      key,
      item: selected.item,
      course: selected.course || (selectedCourse as TrainingCourseRead | null),
      courses: groupCourses.length ? groupCourses : (selected.course ? [selected.course] : []),
      latestRecord,
      history,
      evidence: resolveRecordEvidence(latestRecord, latestFileByRecord, filesById),
      status,
    });
  });

  const priority: Record<string, number> = { Overdue: 0, "Due Soon": 1, Deferred: 2, Scheduled: 3, "Not completed": 4, Current: 5, Completed: 6 };
  return rows.sort((a, b) => Number(b.mandatory) - Number(a.mandatory) || (priority[a.status] ?? 9) - (priority[b.status] ?? 9) || String(a.item.course_name).localeCompare(String(b.item.course_name)));
}

export function RowMenu({ label, children }: { label: string; children: React.ReactNode }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const close = () => panel.current?.hidePopover();
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: Event) => {
      if (!(event.target instanceof Node) || !panel.current?.contains(event.target)) close();
    };
    window.addEventListener("resize", dismiss);
    document.addEventListener("scroll", dismiss, true);
    return () => { window.removeEventListener("resize", dismiss); document.removeEventListener("scroll", dismiss, true); };
  }, [open]);
  const toggle = () => {
    const menu = panel.current;
    const button = trigger.current;
    if (!menu || !button) return;
    if (menu.matches(":popover-open")) { menu.hidePopover(); return; }
    menu.showPopover();
    const anchor = button.getBoundingClientRect();
    const bounds = menu.getBoundingClientRect();
    const spaceBelow = window.innerHeight - anchor.bottom - 12;
    const top = spaceBelow >= bounds.height ? anchor.bottom + 4 : Math.max(8, anchor.top - bounds.height - 4);
    menu.style.top = `${top}px`;
    menu.style.left = `${Math.max(8, Math.min(anchor.right - bounds.width, window.innerWidth - bounds.width - 8))}px`;
    menu.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
  };
  return <div className="trl-menu">
    <button ref={trigger} type="button" className="trl-menu-trigger" aria-label={`Actions for ${label}`} title={`Actions for ${label}`} aria-expanded={open} aria-controls={id} onClick={toggle}><MoreHorizontal size={18} /></button>
    <div ref={panel} id={id} popover="auto" className="trl-menu__panel" role="group" aria-label={`Actions for ${label}`}
      onToggle={(event) => setOpen((event.nativeEvent as ToggleEvent).newState === "open")}
      onClick={(event) => { if ((event.target as Element).closest("button")) { close(); trigger.current?.focus({ preventScroll: true }); } }}
      onKeyDown={(event) => {
        if (event.key === "Escape") { close(); trigger.current?.focus({ preventScroll: true }); }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
          const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
          const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowUp" ? -1 : 1) + buttons.length) % buttons.length;
          buttons[next]?.focus();
        }
      }}>{children}</div>
  </div>;
}
const TrainingRequirementList: React.FC<Props> = (props) => {
  const { items, courses, records, files, canEdit, busy, onEditRecord, onDeleteRecord, onOpenEvidence, onDownloadEvidence, onUploadEvidence, onRecordCompletion } = props;
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(props.initialFilter || "all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const requiredRows = useMemo(() => buildRows(items, courses, records, files), [items, courses, records, files]);
  const otherRows = useMemo(() => {
    const coveredKeys = new Set(requiredRows.map((row) => row.key));
    const coveredIds = new Set<string>();
    const assigned = new Set<string>();
    requiredRows.forEach((row) => {
      row.history.forEach((record) => assigned.add(record.id));
      [row.item.course_id, row.item.course_pk, row.course?.id, row.course?.course_id, row.course?.course_pk]
        .filter(Boolean)
        .forEach((value) => coveredIds.add(String(value)));
      row.courses.forEach((course) => {
        [course.id, course.course_id, course.course_pk].filter(Boolean).forEach((value) => coveredIds.add(String(value)));
      });
    });
    const remaining = records.filter((record) => !assigned.has(record.id));
    const seen = new Set<string>();
    const extraItems: TrainingStatusItem[] = [];
    remaining.slice().sort((a, b) => recordTime(b) - recordTime(a)).forEach((record) => {
      const course = byCourseForHistory(courses, record);
      const id = String(course?.id || record.course_pk || record.course_id || "");
      if (!id || seen.has(id) || coveredIds.has(id) || coveredIds.has(String(record.course_id)) || coveredIds.has(String(record.course_pk || ""))) return;
      if (course && coveredKeys.has(explicitTrainingRequirementKey(course, courses))) return;
      seen.add(id);
      coveredIds.add(id);
      extraItems.push({
        course_id: course?.course_id || record.course_id,
        course_pk: course?.id || record.course_pk,
        course_name: course?.course_name || record.course_name || record.course_id,
        last_completion_date: record.completion_date,
        valid_until: record.valid_until,
        status: isHistorical(record) ? "Historical" : "Recorded",
        is_mandatory: false,
        kind: course?.kind,
        group_code: course?.group_code,
        prerequisite_course_id: course?.prerequisite_course_id,
      });
    });
    return buildRows(extraItems, courses, remaining, files).map((row) => ({
      ...row,
      item: { ...row.item, last_completion_date: row.latestRecord?.completion_date, valid_until: row.latestRecord?.valid_until },
    }));
  }, [requiredRows, records, courses, files]);
  const latestFiles = useMemo(() => latestEvidenceByRecord(files), [files]);
  const fileIds = useMemo(() => filesByIdMap(files), [files]);
  const matches = (row: RequirementRow) => {
    const text = `${row.item.course_name} ${row.course?.course_id || row.item.course_id}`.toLowerCase();
    return text.includes(query.trim().toLowerCase()) && (filter === "all" ||
      (filter === "missing" ? !row.evidence : filter === "incomplete" ? row.mandatory && row.status === "Not completed" : ["Overdue", "Due Soon", "Not completed"].includes(row.status)));
  };
  const groups = [
    { title: "Mandatory courses", icon: ShieldCheck, rows: requiredRows.filter((row) => row.mandatory) },
    { title: "Other training", icon: FileText, rows: [...requiredRows.filter((row) => !row.mandatory), ...otherRows] },
  ];
  const toggle = (key: string) => setExpanded((prev) => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const certificate = (row: RequirementRow, record = row.latestRecord, history = false) => {
    const evidence = history ? resolveRecordEvidence(record, latestFiles, fileIds) : row.evidence;
    const expired = !history && (row.status === "Overdue" || (row.status === "Recorded" && !!record?.valid_until && new Date(`${record.valid_until.slice(0, 10)}T23:59:59`).getTime() < Date.now()));
    const renew = canEdit && !history && (expired || !record) && row.course && onRecordCompletion;
    const attach = canEdit && record && !evidence && onUploadEvidence;
    return <div className="trl-certificate-actions">
      {renew ? <button type="button" className={`trl-file-action ${expired ? "trl-file-action--expired" : ""}`} disabled={busy}
        aria-label={`${expired ? "Upload renewed" : "Upload"} certificate for ${row.item.course_name}`} title={expired ? "Expired — record renewal and upload new certificate" : "Record completion and upload certificate"}
        onClick={() => onRecordCompletion!(row.course!.id)}>
        <span className="trl-file-symbol">{expired ? <FileText size={18} /> : <FilePlus2 size={18} />}{expired && <AlertCircle className="trl-file-alert" size={12} />}</span>
        {expired ? "Renew" : "Upload"}
      </button> : attach ? <button type="button" className="trl-file-action" disabled={busy} aria-label={`Upload certificate for ${row.item.course_name}`} onClick={() => onUploadEvidence!(record!.id)}><FilePlus2 size={18} /> Upload</button> : null}
      {evidence && onDownloadEvidence ? <button type="button" className="trl-file-action" disabled={busy} title={`Download ${evidence.original_filename}`} aria-label={`Download certificate for ${row.item.course_name}`} onClick={() => onDownloadEvidence(evidence)}><Download size={17} />{!renew && "Download"}</button> : null}
      {!evidence && !renew && !attach ? <span className="trl-muted">Missing</span> : null}
    </div>;
  };
  const recordActions = (record: TrainingRecordRead) => <>
    {canEdit && onEditRecord && <button type="button" onClick={() => onEditRecord(record)}><Pencil size={15} /> Edit record</button>}
    {canEdit && onDeleteRecord && <button type="button" className="trl-menu__danger" onClick={() => onDeleteRecord(record)}><Trash2 size={15} /> Delete record</button>}
  </>;
  return <div className="trl-shell" aria-label="Training requirements and record history" aria-busy={busy}>
    {busy && <p role="status" className="trl-muted">Uploading certificate...</p>}
    <div className="trl-toolbar">
      <label className="trl-search"><Search size={16} aria-hidden /><input aria-label="Search training courses" placeholder="Search courses or codes…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <select aria-label="Filter training courses" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">All courses</option><option value="attention">Needs attention</option><option value="incomplete">Missing required courses</option><option value="missing">Missing certificate</option></select>
    </div>
    {groups.map(({ title, icon: Icon, rows }) => {
      const visible = rows.filter(matches);
      if (!rows.length && title === "Other training") return null;
      return <section className="trl-section" key={title} aria-label={title}>
        <header className="trl-section-header"><h3><Icon size={17} aria-hidden />{title}<span className="trl-count">{visible.length}</span></h3></header>
        <div className="trl-table-view"><table className="trl-table">
          <thead><tr><th scope="col">Course</th><th scope="col">Last completed</th><th scope="col">Next due</th><th scope="col">Status</th><th scope="col">Certificate</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{visible.map((row) => <React.Fragment key={row.key}>
            <tr className={expanded.has(row.key) ? "is-expanded" : ""}>
              <td><strong>{row.item.course_name}</strong><small>{row.course?.course_id || row.item.course_id} · {trainingTypeLabel(row.course)}</small></td>
              <td>{formatDate(row.item.last_completion_date)}</td>
              <td>{formatDate(dueDate(row.item))}{row.item.upcoming_event_date && <small>Scheduled {formatDate(row.item.upcoming_event_date)}</small>}</td>
              <td><span className={`trl-status trl-status--${row.status.toLowerCase().replaceAll(" ", "-")}`}>
                {["Current", "Completed"].includes(row.status) ? <CheckCircle2 size={13} /> : ["Overdue", "Not completed"].includes(row.status) ? <AlertCircle size={13} /> : null}{row.status}</span></td>
              <td>{certificate(row)}</td>
              <td><RowMenu label={row.item.course_name}>
                <button type="button" aria-expanded={expanded.has(row.key)} onClick={() => toggle(row.key)}><History size={15} />{expanded.has(row.key) ? "Hide" : "View"} history ({row.history.length})</button>
                {row.evidence && onOpenEvidence && <button type="button" onClick={() => onOpenEvidence(row.evidence!)}><Eye size={15} /> Preview certificate</button>}
                {canEdit && row.course && onRecordCompletion && <button type="button" onClick={() => onRecordCompletion(row.course!.id)}><FilePlus2 size={15} /> Record completion</button>}
                {row.latestRecord && recordActions(row.latestRecord)}
              </RowMenu></td>
            </tr>
            {expanded.has(row.key) && <tr className="trl-history-row"><td colSpan={6}><div className="trl-history"><h4><History size={16} /> Completion history</h4>
              {row.history.length ? row.history.map((record) => <div className="trl-history-entry" key={record.id}><div><strong>{byCourseForHistory(courses, record)?.course_name || row.item.course_name}</strong><small>{formatDate(record.completion_date)} · {isHistorical(record) ? "Historical" : "Recorded"}{record.valid_until ? ` · Valid until ${formatDate(record.valid_until)}` : ""}</small></div>{certificate(row, record, true)}{canEdit && <RowMenu label={`completion on ${formatDate(record.completion_date)}`}>{recordActions(record)}</RowMenu>}</div>) : <p>No completion recorded yet.</p>}
            </div></td></tr>}
          </React.Fragment>)}{!visible.length && <tr><td colSpan={6} className="trl-empty">{rows.length ? "No courses match these filters." : "No mandatory courses assigned."}</td></tr>}</tbody>
        </table></div>
      </section>;
    })}
  </div>;
};
export default TrainingRequirementList;
