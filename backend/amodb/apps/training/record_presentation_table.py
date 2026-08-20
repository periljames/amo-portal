from __future__ import annotations

import html
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from fastapi.responses import HTMLResponse

from ..accounts import models as accounts_models
from . import course_lifecycle as training_course_lifecycle
from . import models as training_models
from . import record_lifecycle as training_record_lifecycle
from . import record_presentation as _base
from . import record_presentation_glass as _glass


_TABLE_CSS = r"""
.record-shell {
  overflow: hidden;
  border-radius: var(--radius-lg);
}
.record-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}
.record-table col.course { width: 46%; }
.record-table col.completed { width: 19%; }
.record-table col.due { width: 21%; }
.record-table col.certificate { width: 14%; }
.record-table thead th {
  padding: 13px 18px 11px;
  border-bottom: 1px solid var(--separator);
  color: var(--tertiary);
  font-size: 10px;
  line-height: 1.2;
  font-weight: 720;
  letter-spacing: .065em;
  text-align: left;
  text-transform: uppercase;
}
.record-table thead th:last-child { text-align: center; }
.record-row { transition: background .15s ease, opacity .15s ease; }
.record-row + .record-row td { border-top: 1px solid var(--separator); }
.record-row:hover { background: rgba(255,255,255,.26); }
.record-row td {
  min-width: 0;
  padding: 17px 18px;
  vertical-align: middle;
}
.course-title {
  display: block;
  overflow-wrap: anywhere;
  color: var(--label);
  font-size: 14px;
  line-height: 1.34;
  font-weight: 680;
  letter-spacing: -.012em;
}
.record-date {
  display: inline-block;
  color: var(--label);
  font-size: 13px;
  line-height: 1.25;
  font-weight: 610;
  font-variant-numeric: tabular-nums;
}
.due-date { font-weight: 680; }
.due-current { color: color-mix(in srgb, var(--green) 76%, var(--label)); }
.due-overdue { color: color-mix(in srgb, var(--red) 82%, var(--label)); }
.due-scheduled { color: color-mix(in srgb, #c57a00 80%, var(--label)); }
.due-neutral { color: var(--label); }
.due-discontinued { color: rgba(60,60,67,.56); }
.record-row.is-discontinued {
  background: rgba(118,118,128,.045);
  opacity: .64;
}
.record-row.is-discontinued .course-title,
.record-row.is-discontinued .record-date { color: rgba(60,60,67,.64); }
.certificate-cell { text-align: center; }
.certificate-icon-button {
  width: 38px;
  height: 38px;
  display: inline-grid;
  place-items: center;
  border: 1px solid rgba(0,122,255,.12);
  border-radius: 12px;
  background: rgba(0,122,255,.075);
  color: var(--blue);
  cursor: pointer;
  transition: transform .14s ease, background .14s ease;
}
.certificate-icon-button:hover { background: rgba(0,122,255,.13); }
.certificate-icon-button:active { transform: scale(.94); }
.certificate-icon-button svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.no-certificate { color: var(--tertiary); font-size: 13px; }
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 13px;
  margin: 10px 3px 0;
  color: var(--tertiary);
  font-size: 10px;
}
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.legend i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.legend .current { color: color-mix(in srgb, var(--green) 76%, var(--label)); }
.legend .overdue { color: color-mix(in srgb, var(--red) 82%, var(--label)); }
.legend .scheduled { color: color-mix(in srgb, #c57a00 80%, var(--label)); }
.legend .discontinued { color: rgba(60,60,67,.56); }
@media (max-width: 700px) {
  .record-shell { background: transparent; border: 0; box-shadow: none; -webkit-backdrop-filter: none; backdrop-filter: none; overflow: visible; }
  .record-table, .record-table tbody { display: block; }
  .record-table colgroup, .record-table thead { display: none; }
  .record-row {
    display: grid;
    grid-template-columns: minmax(0,1fr) auto;
    gap: 12px 14px;
    margin-bottom: 10px;
    padding: 16px;
    border: 1px solid rgba(255,255,255,.66);
    border-radius: 21px;
    background: rgba(255,255,255,.48);
    -webkit-backdrop-filter: saturate(175%) blur(24px);
    backdrop-filter: saturate(175%) blur(24px);
    box-shadow: 0 10px 26px rgba(35,35,45,.05), inset 0 1px 0 rgba(255,255,255,.72);
  }
  .record-row + .record-row td { border-top: 0; }
  .record-row td { display: block; padding: 0; }
  .record-row .course-cell { grid-column: 1 / 2; align-self: center; }
  .record-row .certificate-cell { grid-column: 2 / 3; grid-row: 1 / 2; align-self: center; }
  .record-row .completed-cell, .record-row .due-cell { position: relative; padding-top: 15px; }
  .record-row .completed-cell { grid-column: 1 / 2; }
  .record-row .due-cell { grid-column: 2 / 3; min-width: 116px; }
  .record-row .completed-cell::before, .record-row .due-cell::before {
    position: absolute;
    top: 0;
    left: 0;
    color: var(--tertiary);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: .055em;
    text-transform: uppercase;
  }
  .record-row .completed-cell::before { content: 'Completed'; }
  .record-row .due-cell::before { content: 'Next due'; }
  .legend { margin-top: 9px; }
}
@media print {
  .certificate-icon-button, .legend { display: none !important; }
  .record-shell { border: 1px solid #ddd; box-shadow: none; background: white; }
  .record-row { break-inside: avoid; }
}
"""


def _course_repeats(course: Optional[training_models.TrainingCourse]) -> bool:
    if course is None:
        return False
    if training_course_lifecycle.is_recurrent_course(course):
        return True
    try:
        return int(getattr(course, "frequency_months", None) or 0) > 0
    except (TypeError, ValueError):
        return bool(getattr(course, "frequency_months", None))


def _due_tone(row: dict[str, Any], *, has_recurrence: bool, discontinued: bool) -> str:
    if discontinued:
        return "discontinued"
    if not has_recurrence or not row.get("next_due"):
        return "neutral"
    status = str(row.get("compliance_status") or "").strip().lower()
    if status == "overdue":
        return "overdue"
    if row.get("scheduled") or status in {"scheduled", "due soon", "deferred"}:
        return "scheduled"
    if status in {"current", "completed"}:
        return "current"
    return "neutral"


def _record_history_entry(record: training_models.TrainingRecord, course: Optional[training_models.TrainingCourse]) -> dict[str, Any]:
    return {
        "record_id": str(record.id),
        "type": _base.training_type_label(getattr(course, "kind", None)) if course else "Training",
        "completed": _base._iso(getattr(record, "completion_date", None)),
        "next_due": _base._iso(getattr(record, "valid_until", None)),
        "hours": getattr(record, "hours_completed", None),
        "score": getattr(record, "exam_score", None),
        "certificate_reference": getattr(record, "certificate_reference", None),
    }


def _attach_viewer_bindings(db, *, amo_id: str, user_id: str, requirements: list[dict[str, Any]]) -> None:
    record_ids = {
        str(entry.get("record_id"))
        for row in requirements
        for entry in (row.get("history") or [])
        if entry.get("record_id")
    }
    file_kind_by_record: dict[str, str] = {}
    issue_records: set[str] = set()
    if record_ids:
        approved_files = (
            db.query(training_models.TrainingFile)
            .filter(
                training_models.TrainingFile.amo_id == amo_id,
                training_models.TrainingFile.owner_user_id == user_id,
                training_models.TrainingFile.record_id.in_(record_ids),
                training_models.TrainingFile.kind.in_([
                    training_models.TrainingFileKind.CERTIFICATE,
                    training_models.TrainingFileKind.EVIDENCE,
                ]),
                training_models.TrainingFile.review_status == training_models.TrainingFileReviewStatus.APPROVED,
            )
            .all()
        )
        for file_row in approved_files:
            rid = str(file_row.record_id)
            kind = str(getattr(file_row.kind, "value", file_row.kind))
            if rid not in file_kind_by_record or kind == "CERTIFICATE":
                file_kind_by_record[rid] = kind

        issue_records = {
            str(row[0])
            for row in db.query(training_models.TrainingCertificateIssue.record_id)
            .filter(
                training_models.TrainingCertificateIssue.amo_id == amo_id,
                training_models.TrainingCertificateIssue.record_id.in_(record_ids),
            )
            .all()
            if row[0]
        }

    for row in requirements:
        viewer_record_id = None
        viewer_label = None
        for entry in row.get("history") or []:
            rid = str(entry.get("record_id") or "")
            available = bool(rid and (rid in file_kind_by_record or rid in issue_records))
            entry["viewer_available"] = available
            if available and viewer_record_id is None:
                viewer_record_id = rid
                viewer_label = "View certificate" if file_kind_by_record.get(rid) == "CERTIFICATE" or rid in issue_records else "View evidence"
        row["viewer_record_id"] = viewer_record_id
        row["viewer_label"] = viewer_label
        row["evidence_available"] = bool(viewer_record_id)


def _decorate_lifecycle_rows(db, *, amo_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    requirements = [dict(row) for row in (payload.get("requirements") or [])]

    all_records = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user_id,
            training_models.TrainingRecord.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED,
            training_record_lifecycle.active_records_filter(training_models.TrainingRecord),
        )
        .order_by(training_models.TrainingRecord.completion_date.desc(), training_models.TrainingRecord.created_at.desc())
        .all()
    )
    record_by_id = {str(record.id): record for record in all_records}

    course_ids = {str(record.course_id) for record in all_records if getattr(record, "course_id", None)}
    course_ids.update(str(row.get("course_pk")) for row in requirements if row.get("course_pk"))
    courses = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.id.in_(course_ids or [""]),
        )
        .all()
        if course_ids
        else []
    )
    course_by_id = {str(course.id): course for course in courses}

    represented: set[str] = set()
    for row in requirements:
        history = list(row.get("history") or [])
        represented.update(str(entry.get("record_id")) for entry in history if entry.get("record_id"))
        latest_entry = history[0] if history else None
        latest_record = record_by_id.get(str(latest_entry.get("record_id"))) if latest_entry else None
        latest_course = course_by_id.get(str(getattr(latest_record, "course_id", ""))) if latest_record else None
        primary_course = course_by_id.get(str(row.get("course_pk") or ""))

        # A recurrent family is displayed as the stage most recently completed.
        # This keeps an Initial completion labelled Initial until a Refresher is
        # actually completed, while the recurrent policy still supplies Next due.
        if latest_course and getattr(latest_course, "course_name", None):
            row["course_name"] = str(latest_course.course_name)

        has_recurrence = _course_repeats(primary_course) or _course_repeats(latest_course)
        discontinued = bool(
            (primary_course is not None and getattr(primary_course, "is_active", True) is False)
            or (latest_course is not None and getattr(latest_course, "is_active", True) is False)
        )
        row["has_recurrence"] = has_recurrence
        row["presentation_status"] = "Discontinued" if discontinued else str(row.get("compliance_status") or "")
        row["due_tone"] = _due_tone(row, has_recurrence=has_recurrence, discontinued=discontinued)

    # Preserve verified history for courses that have since been discontinued.
    # They no longer participate in current compliance, so they are added only as
    # greyed historical rows and never change the current/due counters.
    inactive_by_course: dict[str, list[training_models.TrainingRecord]] = defaultdict(list)
    for record in all_records:
        rid = str(record.id)
        if rid in represented:
            continue
        course = course_by_id.get(str(record.course_id))
        if course is not None and getattr(course, "is_active", True) is False:
            inactive_by_course[str(course.id)].append(record)

    for course_id, records in inactive_by_course.items():
        course = course_by_id.get(course_id)
        if course is None:
            continue
        records.sort(
            key=lambda record: (getattr(record, "completion_date", None) or date.min, str(getattr(record, "created_at", ""))),
            reverse=True,
        )
        latest = records[0]
        requirements.append({
            "requirement_key": f"discontinued:{course_id}",
            "course_pk": course_id,
            "course_name": str(getattr(course, "course_name", None) or "Training"),
            "last_completed": _base._iso(getattr(latest, "completion_date", None)),
            "next_due": _base._iso(getattr(latest, "valid_until", None)),
            "scheduled": None,
            "compliance_status": "Discontinued",
            "presentation_status": "Discontinued",
            "has_recurrence": _course_repeats(course),
            "due_tone": "discontinued",
            "history": [_record_history_entry(record, course) for record in records],
        })

    _attach_viewer_bindings(db, amo_id=amo_id, user_id=user_id, requirements=requirements)
    payload["requirements"] = requirements
    return payload


def _history_details(row: dict[str, Any]) -> str:
    history = list(row.get("history") or [])
    older = history[1:]
    if not older:
        return ""
    items = "".join(
        "<li><span>"
        f"{html.escape(str(item.get('type') or 'Training'))}"
        "</span>"
        f"<strong>{_base._fmt_public_date(item.get('completed'))}</strong></li>"
        for item in older
    )
    return f"<div class='sr-only' aria-label='Previous completions'><ul>{items}</ul></div>"


def _training_profile_html(payload: dict[str, Any]) -> HTMLResponse:
    user = payload.get("user") or {}
    tenant = payload.get("tenant") or {}
    summary = payload.get("summary") or {}
    requirements = list(payload.get("requirements") or [])

    org_raw = str(tenant.get("name") or tenant.get("organisation_name") or "Approved Maintenance Organisation")
    person_raw = str(user.get("full_name") or user.get("name") or "Personnel record")
    role_raw = str(user.get("position_title") or user.get("job_title") or user.get("position") or "Personnel")
    org = html.escape(org_raw)
    person = html.escape(person_raw)
    role = html.escape(role_raw)
    user_id = html.escape(str(user.get("user_id") or ""), quote=True)

    accent = str(tenant.get("brand_accent") or "#8a6f20").strip()
    if not accent.startswith("#") or len(accent) not in (4, 7):
        accent = "#8a6f20"
    accent_attr = html.escape(accent, quote=True)

    logo_url = _glass._safe_image_url(tenant.get("logo_url"), tenant.get("brand_logo_url"), tenant.get("public_logo_url"))
    photo_url = _glass._safe_image_url(user.get("photo_url"), user.get("profile_image_url"), user.get("avatar_url"))
    brand_visual = (
        f"<img src='{logo_url}' alt='{org} logo' decoding='async' fetchpriority='high'>"
        if logo_url else html.escape(_base._initials(org_raw))
    )
    avatar_visual = (
        f"<img src='{photo_url}' alt='' decoding='async' fetchpriority='high'>"
        if photo_url else html.escape(_base._initials(person_raw))
    )

    meta: list[str] = []
    staff = user.get("staff_code") or user.get("staff_no")
    licence = user.get("licence_number") or user.get("license_number")
    if staff:
        meta.append(f"<span class='meta-pill'>Staff {html.escape(str(staff))}</span>")
    if licence:
        meta.append(f"<span class='meta-pill'>Licence {html.escape(str(licence))}</span>")
    meta.append(f"<span class='meta-pill'>{'Active' if user.get('is_active', True) else 'Inactive'}</span>")

    current_total = int(summary.get("current", 0) or 0)
    completed_total = int(summary.get("completed", 0) or 0)
    current_label = f"{current_total} current"
    if completed_total:
        current_label += f" · {completed_total} completed"

    exceptions: list[str] = []
    due_soon = int(summary.get("due_soon", 0) or 0)
    overdue = int(summary.get("overdue", 0) or 0)
    deferred = int(summary.get("deferred", 0) or 0)
    if due_soon:
        exceptions.append(f"<span class='exception-pill is-due'>{due_soon} due soon</span>")
    if overdue:
        exceptions.append(f"<span class='exception-pill is-overdue'>{overdue} overdue</span>")
    if deferred:
        exceptions.append(f"<span class='exception-pill is-deferred'>{deferred} deferred</span>")
    if not exceptions:
        exceptions.append("<span class='exception-pill'>No exceptions</span>")

    candidate = next((row for row in requirements if row.get("compliance_status") == "Overdue"), None)
    candidate = candidate or next((row for row in requirements if row.get("next_due") and row.get("due_tone") != "discontinued"), None)
    if candidate:
        next_card = (
            "<section class='next-card glass' aria-label='Next training action'>"
            "<div class='next-orb' aria-hidden='true'>↗</div><div class='next-copy'>"
            "<span class='eyebrow'>Next due</span>"
            f"<strong>{html.escape(str(candidate.get('course_name') or 'Training'))}</strong>"
            f"<div class='next-meta'><span>{_base._fmt_public_date(candidate.get('next_due'))}</span></div>"
            "</div></section>"
        )
    else:
        next_card = (
            "<section class='next-card glass'><div class='next-orb' aria-hidden='true'>✓</div>"
            "<div class='next-copy'><span class='eyebrow'>Training record</span>"
            "<strong>No recurrent deadline is currently recorded</strong></div></section>"
        )

    rows: list[str] = []
    for row in requirements:
        name_raw = str(row.get("course_name") or "Training")
        name = html.escape(name_raw)
        completed = _base._fmt_public_date(row.get("last_completed"))
        next_due = _base._fmt_public_date(row.get("next_due"))
        tone = str(row.get("due_tone") or "neutral")
        discontinued = tone == "discontinued"

        viewer_record_id = row.get("viewer_record_id")
        if viewer_record_id:
            certificate = (
                "<button type='button' class='certificate-icon-button' data-view-certificate "
                f"data-record-id='{html.escape(str(viewer_record_id), quote=True)}' "
                f"data-course-name='{html.escape(name_raw, quote=True)}' "
                f"aria-label='View certificate for {html.escape(name_raw, quote=True)}' title='View certificate'>"
                "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M8 13h8'/><path d='M8 17h5'/></svg>"
                "</button>"
            )
        else:
            certificate = "<span class='no-certificate' aria-label='No certificate available'>—</span>"

        rows.append(
            f"<tr class='record-row{' is-discontinued' if discontinued else ''}'>"
            f"<td class='course-cell'><span class='course-title'>{name}</span>{_history_details(row)}</td>"
            f"<td class='completed-cell'><span class='record-date'>{completed}</span></td>"
            f"<td class='due-cell'><span class='record-date due-date due-{html.escape(tone, quote=True)}'>{next_due}</span></td>"
            f"<td class='certificate-cell'>{certificate}</td>"
            "</tr>"
        )

    if not rows:
        rows.append("<tr class='record-row'><td colspan='4' class='empty-state'>No governed training requirements are published for this personnel record.</td></tr>")

    body = f"""
<main class='report' data-training-report data-user-id='{user_id}' style='--accent:{accent_attr}'>
  <header class='brand-bar glass'>
    <div class='brand-visual'>{brand_visual}</div>
    <div class='brand-copy'><h1>{org}</h1><p>Personnel Training &amp; Compliance Record</p></div>
    <nav class='action-dock' aria-label='Report actions'>
      <button class='icon-button' type='button' data-share-report aria-label='Share report' title='Share report'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 16V3'/><path d='m7 8 5-5 5 5'/><path d='M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7'/></svg>
      </button>
      <button class='icon-button' type='button' data-copy-link aria-label='Copy verification link' title='Copy verification link'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><rect x='9' y='9' width='11' height='11' rx='2'/><path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/></svg>
      </button>
      <button class='icon-button' type='button' data-download-pdf aria-label='Download PDF' title='Download PDF'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M12 12v6'/><path d='m9 15 3 3 3-3'/></svg>
      </button>
      <button class='icon-button' type='button' data-print-report aria-label='Print report' title='Print report'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M6 9V2h12v7'/><path d='M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2'/><rect x='6' y='14' width='12' height='8'/></svg>
      </button>
    </nav>
  </header>

  <section class='profile-hero glass'>
    <div class='avatar' role='img' aria-label='Personnel image'>{avatar_visual}</div>
    <div class='profile-copy'><h2>{person}</h2><p class='role'>{role}</p><div class='profile-meta'>{''.join(meta)}</div></div>
    <span class='verified'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M20 6 9 17l-5-5'/></svg>Verified</span>
  </section>

  <div class='overview'>
    <section class='compliance-card glass' aria-label='Training compliance summary'>
      <div class='current-count'><strong>{current_total}</strong><span>{html.escape(current_label)}</span></div>
      <div class='exception-pills'>{''.join(exceptions)}</div>
    </section>
    {next_card}
  </div>

  <div class='section-head'><div><h3>Training record</h3><p>Verified completion and recurrent due dates</p></div><p>{len(requirements)} entries</p></div>
  <section class='record-shell glass' aria-label='Training record table'>
    <table class='record-table'>
      <colgroup><col class='course'><col class='completed'><col class='due'><col class='certificate'></colgroup>
      <thead><tr><th scope='col'>Course</th><th scope='col'>Completed</th><th scope='col'>Next due</th><th scope='col'>Certificate</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>
  <div class='legend' aria-label='Due date colour key'>
    <span class='current'><i></i>Current</span><span class='overdue'><i></i>Overdue</span><span class='scheduled'><i></i>Scheduled</span><span class='discontinued'><i></i>Discontinued</span>
  </div>
</main>

<dialog id='certificate-viewer' class='certificate-viewer' aria-label='Certificate viewer'>
  <div class='viewer-shell'>
    <header class='viewer-bar'>
      <button type='button' class='close-button' data-close-viewer aria-label='Close certificate viewer'>
        <svg viewBox='0 0 24 24' aria-hidden='true'><path d='m6 6 12 12'/><path d='M18 6 6 18'/></svg>
      </button>
      <div class='viewer-heading'><strong data-viewer-title>Training certificate</strong><span>Verified controlled evidence</span></div>
      <a class='open-original' data-open-certificate target='_blank' rel='noopener'>Open original</a>
    </header>
    <div class='certificate-stage' data-certificate-stage></div>
  </div>
</dialog>
<div class='action-feedback' data-action-feedback role='status' aria-live='polite'></div>
"""

    css = f"{_glass._GLASS_CSS}\n{_TABLE_CSS}"
    return HTMLResponse(
        content=(
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='color-scheme' content='light'>"
            f"<meta name='theme-color' content='{accent_attr}'>"
            f"<title>{person} · Training verification</title><style>{css}</style>"
            "<script src='/public/training/assets/record-report.js' defer></script>"
            f"</head><body style='--accent:{accent_attr}'>{body}</body></html>"
        )
    )


def install_training_record_presentation(router_module) -> None:
    """Install the lifecycle table on top of the signed glass report endpoints."""
    if getattr(router_module, "_table_training_record_presentation_installed", False):
        return

    _glass.install_training_record_presentation(router_module)
    glass_payload = router_module._public_training_profile_payload

    def public_payload(db, *, amo_id: str, user_id: str, record_id: Optional[str] = None):
        payload = glass_payload(db, amo_id=amo_id, user_id=user_id, record_id=record_id)
        return _decorate_lifecycle_rows(db, amo_id=amo_id, user_id=user_id, payload=payload)

    router_module._public_training_profile_payload = public_payload
    router_module._training_profile_html = _training_profile_html
    router_module._table_training_record_presentation_installed = True


__all__ = [
    "_TABLE_CSS",
    "_decorate_lifecycle_rows",
    "_due_tone",
    "_training_profile_html",
    "install_training_record_presentation",
]
