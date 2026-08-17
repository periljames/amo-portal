import React, { useMemo, useRef } from "react";

import type { TrainingFileRead } from "../../services/training";
import type { TrainingCourseRead, TrainingRecordRead, TrainingStatusItem } from "../../types/training";
import {
  canonicalTrainingType,
  complianceStatusLabel,
  explicitTrainingRequirementKey,
  isNonRecurrentInitial,
  trainingTypeLabel,
} from "../../utils/trainingPresentation";
import "./TrainingRequirementList.css";

type Props = {
  items: TrainingStatusItem[];
  courses: TrainingCourseRead[];
  records: TrainingRecordRead[];
  files: TrainingFileRead[];
  canEdit: boolean;
  onEditRecord?: (record: TrainingRecordRead) => void;
  onDeleteRecord?: (record: TrainingRecordRead) => void;
  onOpenEvidence?: (file: TrainingFileRead) => void;
  onUploadEvidence?: (recordId: string) => void;
  onRecordCompletion?: (coursePk: string) => void;
};

type RequirementRow = {
  key: string;
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
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function dueDate(item: TrainingStatusItem): string | null {
  return item.extended_due_date || item.valid_until || null;
}

function recordTime(record: TrainingRecordRead): number {
  const raw = record.completion_date || record.created_at || "";
  const parsed = new Date(raw.includes("T") ? raw : `${raw}T12:00:00`).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function isHistorical(record: TrainingRecordRead): boolean {
  const state = String(record.record_status || record.source_status || "ACTIVE").trim().toUpperCase();
  return ["RENEWED", "SUPERSEDED", "INACTIVE"].includes(state);
}

function RowActionMenu({ label, children }: { label: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const timer = useRef<number | null>(null);
  const open = () => ref.current?.setAttribute("open", "");
  const cancel = () => {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  return (
    <details
      ref={ref}
      className="trl-menu"
      onContextMenu={(event) => { event.preventDefault(); open(); }}
      onPointerDown={(event) => {
        if (event.pointerType !== "mouse") timer.current = window.setTimeout(open, 650);
      }}
      onPointerUp={cancel}
      onPointerCancel={cancel}
      onPointerMove={cancel}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          ref.current?.removeAttribute("open");
          (ref.current?.querySelector("summary") as HTMLElement | null)?.focus();
        }
      }}
    >
      <summary aria-label={`Actions for ${label}`}>⋯</summary>
      <div className="trl-menu__panel" role="menu">{children}</div>
    </details>
  );
}

function buildRows(items: TrainingStatusItem[], courses: TrainingCourseRead[], records: TrainingRecordRead[], files: TrainingFileRead[]): RequirementRow[] {
  const byCourse = new Map<string, TrainingCourseRead>();
  courses.forEach((course) => {
    if (course.id) byCourse.set(String(course.id), course);
    if (course.course_id) byCourse.set(String(course.course_id), course);
  });

  const requirementKey = (course: TrainingCourseRead | null): string => {
    if (!course) return "unknown";
    const direct = explicitTrainingRequirementKey(course);
    if (!direct.startsWith("course:")) return direct;
    const code = String(course.course_id || "").trim().toLocaleLowerCase();
    if (!code) return direct;
    const recurrent = courses.find((candidate) => String(candidate.prerequisite_course_id || "").trim().toLocaleLowerCase() === code);
    return recurrent ? explicitTrainingRequirementKey(recurrent) : direct;
  };

  const grouped = new Map<string, Array<{ item: TrainingStatusItem; course: TrainingCourseRead | null }>>();
  items.forEach((item) => {
    const course = byCourse.get(String(item.course_id)) || courses.find((candidate) => candidate.course_name === item.course_name) || null;
    const key = requirementKey(course);
    const list = grouped.get(key) || [];
    list.push({ item, course });
    grouped.set(key, list);
  });

  const latestFileByRecord = new Map<string, TrainingFileRead>();
  files.slice().sort((a, b) => String(b.uploaded_at).localeCompare(String(a.uploaded_at))).forEach((file) => {
    if (file.record_id && !latestFileByRecord.has(file.record_id)) latestFileByRecord.set(file.record_id, file);
  });

  const rows: RequirementRow[] = [];
  grouped.forEach((members, key) => {
    const selected = members.slice().sort((a, b) => {
      const rank = (value: typeof a) => canonicalTrainingType(value.course) === "RECURRENT" ? 2 : canonicalTrainingType(value.course) === "INITIAL" ? 1 : 0;
      return rank(b) - rank(a);
    })[0];
    const groupCourses = members.map((member) => member.course).filter(Boolean) as TrainingCourseRead[];
    const ids = new Set<string>();
    groupCourses.forEach((course) => { if (course.id) ids.add(String(course.id)); if (course.course_id) ids.add(String(course.course_id)); });
    const history = records.filter((record) => ids.has(String(record.course_id)) || ids.has(String(record.course_pk || ""))).sort((a, b) => recordTime(b) - recordTime(a));
    const latestRecord = history.find((record) => !isHistorical(record)) || history[0] || null;
    let status = complianceStatusLabel(selected.item.status);
    if (status === "Current" && isNonRecurrentInitial(selected.course)) status = "Completed";
    rows.push({
      key,
      item: selected.item,
      course: selected.course,
      courses: groupCourses,
      latestRecord,
      history,
      evidence: latestRecord ? latestFileByRecord.get(latestRecord.id) || null : null,
      status,
    });
  });

  const priority: Record<string, number> = { Overdue: 0, "Due Soon": 1, Deferred: 2, Scheduled: 3, "Not completed": 4, Current: 5, Completed: 6 };
  return rows.sort((a, b) => (priority[a.status] ?? 9) - (priority[b.status] ?? 9) || String(a.item.course_name).localeCompare(String(b.item.course_name)));
}

const TrainingRequirementList: React.FC<Props> = ({ items, courses, records, files, canEdit, onEditRecord, onDeleteRecord, onOpenEvidence, onUploadEvidence, onRecordCompletion }) => {
  const rows = useMemo(() => buildRows(items, courses, records, files), [items, courses, records, files]);

  const actions = (row: RequirementRow) => (
    <RowActionMenu label={row.item.course_name}>
      {row.latestRecord && onEditRecord && canEdit ? <button type="button" role="menuitem" onClick={() => onEditRecord(row.latestRecord!)}>Edit record</button> : null}
      {row.evidence && onOpenEvidence ? <button type="button" role="menuitem" onClick={() => onOpenEvidence(row.evidence!)}>Open certificate/evidence</button> : null}
      {row.latestRecord && !row.evidence && onUploadEvidence ? <button type="button" role="menuitem" onClick={() => onUploadEvidence(row.latestRecord!.id)}>Attach certificate/evidence</button> : null}
      {canEdit && row.course && onRecordCompletion ? <button type="button" role="menuitem" onClick={() => onRecordCompletion(row.course!.id)}>Record completion</button> : null}
      {row.latestRecord && onDeleteRecord && canEdit ? <button type="button" role="menuitem" className="trl-menu__danger" onClick={() => onDeleteRecord(row.latestRecord!)}>Delete record</button> : null}
    </RowActionMenu>
  );

  if (!rows.length) return <div className="trl-empty">No applicable training requirements are available for this person.</div>;

  return (
    <div className="trl-shell" aria-label="Training requirements">
      <div className="trl-table-view">
        <table className="trl-table">
          <thead><tr><th>Training</th><th>Last Completed</th><th>Next Due</th><th>Status</th><th>Evidence</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.key} onContextMenu={(event) => {
            event.preventDefault();
            event.currentTarget.querySelector("details")?.setAttribute("open", "");
          }}>
            <td><strong>{row.item.course_name}</strong><small>{row.course?.course_id || row.item.course_id} · {trainingTypeLabel(row.course)}</small><details className="trl-details"><summary>View details</summary><dl><dt>Compliance Status</dt><dd>{row.status}</dd><dt>Last Completed</dt><dd>{formatDate(row.item.last_completion_date)}</dd><dt>Next Due</dt><dd>{formatDate(dueDate(row.item))}</dd><dt>Scheduled</dt><dd>{row.item.upcoming_event_date ? formatDate(row.item.upcoming_event_date) : "Not scheduled"}</dd></dl><h4>Training history</h4>{row.history.length ? <ul>{row.history.map((record) => { const course = byCourseForHistory(courses, record); return <li key={record.id}><b>{trainingTypeLabel(course)}</b> · Completed {formatDate(record.completion_date)}</li>; })}</ul> : <p>No verified completion history.</p>}</details></td>
            <td>{formatDate(row.item.last_completion_date)}</td>
            <td><strong>{formatDate(dueDate(row.item))}</strong><small>Scheduled {row.item.upcoming_event_date ? formatDate(row.item.upcoming_event_date) : "—"}</small></td>
            <td><span className={`trl-status trl-status--${row.status.toLocaleLowerCase().replaceAll(" ", "-")}`}>{row.status}</span></td>
            <td>{row.evidence ? <button type="button" className="trl-evidence" onClick={() => onOpenEvidence?.(row.evidence!)}>Available</button> : "—"}</td>
            <td>{actions(row)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="trl-card-view">{rows.map((row) => <article className="trl-card" key={row.key} onContextMenu={(event) => { event.preventDefault(); event.currentTarget.querySelector("details.trl-menu")?.setAttribute("open", ""); }}>
        <header><div><h3>{row.item.course_name}</h3><small>{row.course?.course_id || row.item.course_id} · {trainingTypeLabel(row.course)}</small></div><span className={`trl-status trl-status--${row.status.toLocaleLowerCase().replaceAll(" ", "-")}`}>{row.status}</span></header>
        <dl><dt>Completed</dt><dd>{formatDate(row.item.last_completion_date)}</dd><dt>Next Due</dt><dd>{formatDate(dueDate(row.item))}</dd><dt>Scheduled</dt><dd>{row.item.upcoming_event_date ? formatDate(row.item.upcoming_event_date) : "—"}</dd></dl>
        <footer><span>{row.evidence ? "Certificate/evidence available" : "No linked evidence"}</span>{actions(row)}</footer>
        <details className="trl-details"><summary>View details and history</summary>{row.history.length ? <ul>{row.history.map((record) => { const course = byCourseForHistory(courses, record); return <li key={record.id}><b>{trainingTypeLabel(course)}</b> · Completed {formatDate(record.completion_date)}</li>; })}</ul> : <p>No verified completion history.</p>}</details>
      </article>)}</div>
    </div>
  );
};

function byCourseForHistory(courses: TrainingCourseRead[], record: TrainingRecordRead): TrainingCourseRead | null {
  return courses.find((course) => String(course.id) === String(record.course_id) || String(course.course_id) === String(record.course_id)) || null;
}

export default TrainingRequirementList;
