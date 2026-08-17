from __future__ import annotations

import html
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Iterable, Optional
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from sqlalchemy.orm import noload

from ..accounts import models as accounts_models
from . import compliance as training_compliance
from . import models as training_models
from . import record_lifecycle as training_record_lifecycle


_STATUS_LABELS = {
    "OK": "Current",
    "DUE_SOON": "Due Soon",
    "OVERDUE": "Overdue",
    "DEFERRED": "Deferred",
    "SCHEDULED_ONLY": "Scheduled",
    "NOT_DONE": "Not completed",
}


def normalized_training_kind(value: Any) -> str:
    """Return the canonical lifecycle type without mutating historical codes.

    REFRESHER remains readable from legacy rows but is presented and evaluated as
    RECURRENT. CONTINUATION is also recurrent lifecycle training, not a third
    user-facing primary type.
    """

    raw = getattr(value, "value", value)
    normalized = str(raw or "").strip().upper()
    if normalized in {"REFRESHER", "RECURRENT", "CONTINUATION", "RENEWAL"}:
        return "RECURRENT"
    if normalized == "INITIAL":
        return "INITIAL"
    return normalized or "OTHER"


def training_type_label(value: Any) -> str:
    kind = normalized_training_kind(value)
    if kind == "INITIAL":
        return "Initial"
    if kind == "RECURRENT":
        return "Recurrent"
    return "—"


def is_initial_course_explicit(course: training_models.TrainingCourse) -> bool:
    if normalized_training_kind(getattr(course, "kind", None)) == "INITIAL":
        return True
    return str(getattr(course, "status", "") or "").strip().upper() == "INITIAL"


def is_recurrent_course_explicit(course: training_models.TrainingCourse) -> bool:
    if normalized_training_kind(getattr(course, "kind", None)) == "RECURRENT":
        return True
    return str(getattr(course, "status", "") or "").strip().upper() in {"RECURRENT", "REFRESHER", "CONTINUATION", "RENEWAL"}


def explicit_recurrence_key(course: training_models.TrainingCourse, courses: Iterable[training_models.TrainingCourse] = ()) -> str:
    """Group only when the catalogue declares the relationship.

    `group_code` is preferred. A declared prerequisite relationship is the
    compatibility fallback. Course-code suffixes and title words are never used.
    """

    group_code = str(getattr(course, "group_code", "") or "").strip()
    if group_code:
        return f"group:{group_code.casefold()}"

    prereq = str(getattr(course, "prerequisite_course_id", "") or "").strip()
    if prereq:
        return f"prerequisite:{prereq.casefold()}"

    code = str(getattr(course, "course_id", "") or "").strip()
    if code:
        for candidate in courses:
            declared = str(getattr(candidate, "prerequisite_course_id", "") or "").strip()
            if declared and declared.casefold() == code.casefold():
                return f"prerequisite:{code.casefold()}"

    return f"course:{getattr(course, 'id', code)}"


def mask_public_phone(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 7:
        return "***"
    if raw.startswith("+") and len(digits) >= 9:
        country_len = max(1, len(digits) - 9)
        country = digits[:country_len]
        local = digits[country_len:]
        return f"+{country} {local[:3]} *** {local[-3:]}"
    return f"{digits[:4]} *** {digits[-3:]}"


def mask_public_email(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or "@" not in raw:
        return None if not raw else "***"
    local, domain = raw.rsplit("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}***"
    else:
        masked_local = f"{local[0]}***{local[-2:]}"
    return f"{masked_local}@{domain}"


def mask_public_identifier(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) <= 4:
        return raw
    return f"{raw[:2]}***{raw[-2:]}"


def _canonical_origin_candidates(db, amo: Optional[accounts_models.AMO]) -> list[str]:
    candidates: list[str] = []
    if amo is not None:
        # Future/extended tenant schemas may expose one of these. getattr keeps
        # this layer compatible with current deployments where AMO has no URL.
        for attr in ("public_base_url", "public_url", "public_domain"):
            value = getattr(amo, attr, None)
            if value:
                candidates.append(str(value))
    if db is not None:
        try:
            settings = db.query(accounts_models.PlatformSettings).first()
        except Exception:
            settings = None
        if settings is not None and getattr(settings, "api_base_url", None):
            candidates.append(str(settings.api_base_url))
    for env_name in ("APP_PUBLIC_BASE_URL", "PUBLIC_APP_URL", "PLATFORM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL"):
        value = os.getenv(env_name)
        if value:
            candidates.append(value)
    return candidates


def canonical_public_origin(db=None, amo: Optional[accounts_models.AMO] = None) -> str:
    """Return an explicit, stable HTTPS origin for permanent verification URLs.

    This deliberately never falls back to Request/Host headers and never emits a
    relative URL. Misconfiguration fails closed instead of producing a QR that
    only works from the page where it was generated.
    """

    for candidate in _canonical_origin_candidates(db, amo):
        raw = candidate.strip()
        if not raw:
            continue
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlsplit(raw)
        if not parsed.hostname:
            continue
        if parsed.scheme.lower() != "https":
            continue
        return urlunsplit(("https", parsed.netloc, "", "", "")).rstrip("/")
    raise RuntimeError("Canonical HTTPS public origin is not configured for Training verification URLs.")


def absolute_training_verification_url(*, db, user_id: str, amo: Optional[accounts_models.AMO], report_token: Optional[str]) -> str:
    origin = canonical_public_origin(db, amo)
    public_identifier = (
        getattr(amo, "login_slug", None)
        or getattr(amo, "amo_code", None)
        or getattr(amo, "id", None)
        or ""
    )
    params: list[tuple[str, str]] = [("format", "html")]
    if public_identifier:
        params.append(("amo", str(public_identifier)))
    if report_token:
        params.append(("report_token", str(report_token)))
    path = f"/public/training/users/{quote(str(user_id), safe='')}/verify"
    return f"{origin}{path}?{urlencode(params)}"


def _record_kind(course: Optional[training_models.TrainingCourse]) -> str:
    return normalized_training_kind(getattr(course, "kind", None)) if course else "OTHER"


def _status_label(item: Any, course: training_models.TrainingCourse) -> str:
    status = str(getattr(item, "status", "") or "").upper()
    if (
        status == "OK"
        and is_initial_course_explicit(course)
        and not getattr(course, "frequency_months", None)
    ):
        return "Completed"
    return _STATUS_LABELS.get(status, status.replace("_", " ").title() or "Not completed")


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_requirement_rows(db, *, amo_id: str, user: accounts_models.User) -> list[dict[str, Any]]:
    required_ids = training_compliance.get_required_course_ids_for_user(db, user)
    if not required_ids:
        return []

    courses = (
        db.query(training_models.TrainingCourse)
        .options(noload("*"))
        .filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.id.in_(required_ids),
            training_models.TrainingCourse.is_active.is_(True),
        )
        .all()
    )
    course_by_id = {str(course.id): course for course in courses}
    course_by_code = {str(course.course_id): course for course in courses}

    evaluation = training_compliance.evaluate_user_training_policy(db, user, required_only=True)
    status_by_code = {str(item.course_id): item for item in evaluation.items}

    records = (
        db.query(training_models.TrainingRecord)
        .options(noload("*"))
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.user_id == user.id,
            training_models.TrainingRecord.course_id.in_(required_ids),
            training_models.TrainingRecord.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED,
            training_record_lifecycle.active_records_filter(training_models.TrainingRecord),
        )
        .order_by(training_models.TrainingRecord.completion_date.desc(), training_models.TrainingRecord.created_at.desc())
        .all()
    )

    records_by_course: dict[str, list[Any]] = defaultdict(list)
    for record in records:
        records_by_course[str(record.course_id)].append(record)

    record_ids = [str(record.id) for record in records]
    evidence_record_ids: set[str] = set()
    if record_ids:
        evidence_record_ids = {
            str(row[0])
            for row in db.query(training_models.TrainingFile.record_id)
            .filter(
                training_models.TrainingFile.amo_id == amo_id,
                training_models.TrainingFile.record_id.in_(record_ids),
                training_models.TrainingFile.kind.in_([
                    training_models.TrainingFileKind.CERTIFICATE,
                    training_models.TrainingFileKind.EVIDENCE,
                ]),
            )
            .all()
            if row[0]
        }

    grouped: dict[str, list[training_models.TrainingCourse]] = defaultdict(list)
    for course in courses:
        grouped[explicit_recurrence_key(course, courses)].append(course)

    rows: list[dict[str, Any]] = []
    for group_key, group_courses in grouped.items():
        recurrent = [course for course in group_courses if is_recurrent_course_explicit(course)]
        initial = [course for course in group_courses if is_initial_course_explicit(course)]
        primary = recurrent[0] if recurrent else (initial[0] if initial else group_courses[0])
        item = status_by_code.get(str(primary.course_id))
        if item is None:
            # A declared recurrent course may be intentionally gated until its
            # prerequisite Initial has been completed. The Initial requirement
            # remains the controlling row in that state.
            for candidate in initial + group_courses:
                candidate_item = status_by_code.get(str(candidate.course_id))
                if candidate_item is not None:
                    primary, item = candidate, candidate_item
                    break
        if item is None:
            continue

        group_records: list[Any] = []
        for course in group_courses:
            group_records.extend(records_by_course.get(str(course.id), []))
        group_records.sort(key=lambda record: (record.completion_date or date.min, record.created_at or datetime.min), reverse=True)
        latest_record = group_records[0] if group_records else None
        latest_course = course_by_id.get(str(getattr(latest_record, "course_id", ""))) if latest_record else None
        latest_type = training_type_label(getattr(latest_course or primary, "kind", None))

        history: list[dict[str, Any]] = []
        for record in group_records:
            record_course = course_by_id.get(str(record.course_id))
            history.append({
                "record_id": str(record.id),
                "type": training_type_label(getattr(record_course, "kind", None)),
                "course_code": getattr(record_course, "course_id", None),
                "completed": _iso(record.completion_date),
                "next_due": _iso(record.valid_until),
                "hours": getattr(record, "training_hours", None),
                "score": getattr(record, "exam_score", None),
                "certificate_reference": getattr(record, "certificate_reference", None),
                "evidence_available": str(record.id) in evidence_record_ids,
            })

        next_due = getattr(item, "extended_due_date", None) or getattr(item, "valid_until", None)
        scheduled = getattr(item, "upcoming_event_date", None)
        rows.append({
            "requirement_key": group_key,
            "course_pk": str(primary.id),
            "course_id": str(primary.course_id),
            "course_name": str(primary.course_name),
            "course_type": latest_type if latest_record else training_type_label(primary.kind),
            "last_completed": _iso(getattr(item, "last_completion_date", None)),
            "next_due": _iso(next_due),
            "scheduled": _iso(scheduled),
            "compliance_status": _status_label(item, primary),
            "evidence_available": any(entry["evidence_available"] for entry in history),
            "record_count": len(history),
            "history": history,
        })

    priority = {"Overdue": 0, "Due Soon": 1, "Deferred": 2, "Scheduled": 3, "Not completed": 4, "Current": 5, "Completed": 6}
    rows.sort(key=lambda row: (priority.get(row["compliance_status"], 9), row["course_name"].casefold()))
    return rows


def _augment_public_payload(original_payload, db, *, amo_id: str, user_id: str, record_id: Optional[str] = None):
    payload = original_payload(db, amo_id=amo_id, user_id=user_id, record_id=record_id)
    user = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == amo_id, accounts_models.User.id == user_id)
        .first()
    )
    if user is None:
        return payload

    rows = _build_requirement_rows(db, amo_id=amo_id, user=user)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["compliance_status"]] += 1

    public_user = dict(payload.get("user") or {})
    for key in ("email", "contact_email"):
        if key in public_user:
            public_user[key] = mask_public_email(public_user.get(key))
    for key in ("phone", "phone_number", "contact_phone"):
        if key in public_user:
            public_user[key] = mask_public_phone(public_user.get(key))

    tenant = dict(payload.get("tenant") or {})
    tenant.setdefault("name", getattr(user.amo, "name", None) if getattr(user, "amo", None) else None)
    tenant.setdefault("contact_email", mask_public_email(getattr(user.amo, "contact_email", None) if getattr(user, "amo", None) else None))
    tenant.setdefault("contact_phone", mask_public_phone(getattr(user.amo, "contact_phone", None) if getattr(user, "amo", None) else None))
    try:
        settings = db.query(accounts_models.PlatformSettings).first()
    except Exception:
        settings = None
    if settings is not None:
        tenant.setdefault("brand_accent", getattr(settings, "brand_accent", None))
        tenant.setdefault("brand_accent_secondary", getattr(settings, "brand_accent_secondary", None))

    payload["user"] = public_user
    payload["tenant"] = tenant
    payload["requirements"] = rows
    payload["summary"] = {
        "requirements": len(rows),
        "current": counts.get("Current", 0),
        "completed": counts.get("Completed", 0),
        "due_soon": counts.get("Due Soon", 0),
        "overdue": counts.get("Overdue", 0),
        "deferred": counts.get("Deferred", 0),
        "scheduled": counts.get("Scheduled", 0),
        "not_completed": counts.get("Not completed", 0),
        "historical_records": sum(row["record_count"] for row in rows),
    }
    # Do not serialize the legacy peer-event list to the public client. It was
    # the source of historical Initial events being labelled Current.
    payload.pop("records", None)
    return payload


def _fmt_public_date(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        parsed = date.fromisoformat(value[:10])
        return parsed.strftime("%d %b %Y")
    except Exception:
        return html.escape(value)


def _initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "?"


def _training_profile_html(payload: dict[str, Any]):
    # Imported lazily to avoid coupling this module to FastAPI during domain-only tests.
    from fastapi.responses import HTMLResponse

    user = payload.get("user") or {}
    tenant = payload.get("tenant") or {}
    summary = payload.get("summary") or {}
    requirements = payload.get("requirements") or []
    org_name = html.escape(str(tenant.get("name") or tenant.get("organisation_name") or "Approved Maintenance Organisation"))
    person_name = html.escape(str(user.get("full_name") or user.get("name") or "Personnel record"))
    title = html.escape(str(user.get("position_title") or user.get("job_title") or user.get("position") or "Personnel"))
    staff = html.escape(str(user.get("staff_code") or user.get("staff_no") or "—"))
    licence = html.escape(str(user.get("licence_number") or user.get("license_number") or "—"))
    profile_state = "Active" if user.get("is_active", True) else "Inactive"
    accent = str(tenant.get("brand_accent") or "#8a6f20")
    if not accent.startswith("#") or len(accent) not in (4, 7):
        accent = "#8a6f20"

    exception = next((row for row in requirements if row.get("compliance_status") == "Overdue"), None)
    if exception:
        next_block = f"<strong>ACTION REQUIRED</strong><span>{html.escape(exception['course_name'])}</span><span>Next Due: {_fmt_public_date(exception.get('next_due'))}</span><b>OVERDUE</b>"
    else:
        candidate = next((row for row in requirements if row.get("next_due")), None)
        if candidate:
            scheduled = _fmt_public_date(candidate.get("scheduled")) if candidate.get("scheduled") else "Not scheduled"
            next_block = f"<strong>NEXT TRAINING</strong><span>{html.escape(candidate['course_name'])}</span><span>Next Due: {_fmt_public_date(candidate.get('next_due'))}</span><span>Scheduled: {scheduled}</span>"
        else:
            next_block = "<strong>TRAINING STATUS</strong><span>No recurrent training deadline is currently recorded.</span>"

    cards: list[str] = []
    table_rows: list[str] = []
    for row in requirements:
        name = html.escape(str(row.get("course_name") or "Training"))
        code = html.escape(str(row.get("course_id") or ""))
        course_type = html.escape(str(row.get("course_type") or "—"))
        status = html.escape(str(row.get("compliance_status") or ""))
        completed = _fmt_public_date(row.get("last_completed"))
        next_due = _fmt_public_date(row.get("next_due"))
        scheduled = _fmt_public_date(row.get("scheduled"))
        evidence = "Certificate/evidence available" if row.get("evidence_available") else "No public evidence link"
        history_items = "".join(
            f"<li><b>{html.escape(str(item.get('type') or 'Training'))}</b> · Completed {_fmt_public_date(item.get('completed'))}</li>"
            for item in row.get("history") or []
        ) or "<li>No verified completion record.</li>"
        ref = html.escape(str(row.get("requirement_key") or row.get("course_id") or ""), quote=True)
        details = f"<details class='row-details'><summary>View details</summary><dl><dt>Compliance Status</dt><dd>{status}</dd><dt>Last Completed</dt><dd>{completed}</dd><dt>Next Due</dt><dd>{next_due}</dd><dt>Scheduled</dt><dd>{scheduled}</dd><dt>Latest training</dt><dd>{course_type} · {code}</dd></dl><h4>Training history</h4><ul>{history_items}</ul></details>"
        menu = f"<details class='row-menu'><summary aria-label='Actions for {name}'>⋯</summary><div role='menu'><button type='button' data-copy='{ref}'>Copy record reference</button></div></details>"
        cards.append(f"<article class='training-card' data-action-row><header><div><h3>{name}</h3><small>{code} · {course_type}</small></div><span class='status status-{status.lower().replace(' ', '-')}'>{status}</span></header><dl><dt>Completed</dt><dd>{completed}</dd><dt>Next Due</dt><dd>{next_due}</dd><dt>Scheduled</dt><dd>{scheduled}</dd></dl><footer><span>{evidence}</span>{menu}</footer>{details}</article>")
        table_rows.append(f"<tr data-action-row><td><strong>{name}</strong><small>{code} · {course_type}</small>{details}</td><td>{completed}</td><td>{next_due}<small>Scheduled {scheduled}</small></td><td><span class='status status-{status.lower().replace(' ', '-')}'>{status}</span></td><td>{'Available' if row.get('evidence_available') else '—'}</td><td>{menu}</td></tr>")

    css = f"""
:root{{--accent:{accent};--ink:#17212b;--muted:#667085;--line:#e4e7ec;--surface:#fff;--bg:#f4f6f8;--danger:#b42318;--warning:#b54708;--ok:#067647}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,Arial,sans-serif}}main{{max-width:1180px;margin:auto;padding:clamp(12px,3vw,32px)}}.mast{{display:flex;gap:18px;align-items:center;border-top:6px solid var(--accent);padding:20px 0 14px}}.brand-mark,.avatar{{display:grid;place-items:center;background:var(--accent);color:white;font-weight:800}}.brand-mark{{width:54px;height:54px;border-radius:10px}}.mast h1{{font-size:clamp(18px,3vw,28px);margin:0}}.mast p{{margin:2px 0;color:var(--muted)}}.verified{{margin-left:auto;border:1px solid #a6f4c5;background:#ecfdf3;color:#067647;border-radius:999px;padding:7px 12px;font-weight:800}}.identity{{display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center;background:white;border:1px solid var(--line);border-radius:14px;padding:16px}}.avatar{{width:84px;aspect-ratio:4/5;border-radius:10px;font-size:26px}}.identity h2{{margin:0}}.identity p{{margin:3px 0;color:var(--muted)}}.meta{{display:flex;gap:16px;flex-wrap:wrap;font-size:13px}}.qr-label{{text-align:right;color:var(--muted);font-size:12px}}.summary{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}.metric{{background:white;border:1px solid var(--line);border-radius:10px;padding:9px 13px;font-weight:700}}.next-action{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 14px;border-left:4px solid var(--accent);background:#fff;border-radius:8px;margin-bottom:14px}}.next-action strong{{letter-spacing:.04em}}.training-shell{{container-type:inline-size;background:white;border:1px solid var(--line);border-radius:14px;overflow:hidden}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.04em}}td small,td strong{{display:block}}td small{{color:var(--muted);margin-top:2px}}.cards{{display:none}}.status{{display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;font-size:12px;font-weight:800;border:1px solid currentColor}}.status-overdue{{color:var(--danger)}}.status-due-soon{{color:var(--warning)}}.status-current,.status-completed{{color:var(--ok)}}.row-menu{{position:relative}}.row-menu>summary{{list-style:none;cursor:pointer;font-size:22px;min-width:44px;min-height:44px;display:grid;place-items:center;border-radius:8px}}.row-menu>summary:focus-visible,.row-details>summary:focus-visible,button:focus-visible{{outline:3px solid var(--accent);outline-offset:2px}}.row-menu>div{{position:absolute;right:0;z-index:4;background:#fff;border:1px solid var(--line);box-shadow:0 8px 30px #10182822;padding:6px;border-radius:9px;min-width:190px}}button{{width:100%;border:0;background:white;padding:10px;text-align:left;cursor:pointer}}.row-details{{margin-top:7px}}.row-details>summary{{cursor:pointer;color:#344054;font-weight:700}}.row-details dl,.training-card dl{{display:grid;grid-template-columns:auto 1fr;gap:5px 12px}}dt{{color:var(--muted)}}dd{{margin:0;font-weight:650}}.training-card{{padding:14px;border-bottom:1px solid var(--line)}}.training-card header,.training-card footer{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}}.training-card h3{{margin:0;font-size:16px}}.training-card small{{color:var(--muted)}}.training-card footer{{align-items:center;border-top:1px solid var(--line);padding-top:8px;font-size:13px;color:var(--muted)}}.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}}
@container (max-width:760px){{table{{display:none}}.cards{{display:block}}}}
@media(max-width:600px){{main{{padding:10px}}.mast{{align-items:flex-start}}.brand-mark{{width:44px;height:44px}}.verified{{font-size:11px}}.identity{{grid-template-columns:auto 1fr}}.qr-label{{display:none}}.avatar{{width:64px}}.metric{{flex:1 1 42%;text-align:center}}}}
@media print{{body{{background:#fff}}main{{max-width:none;padding:0}}.row-menu,.row-details{{display:none}}.training-shell{{border:0}}}}
"""

    body = f"""
<main>
<header class='mast'><div class='brand-mark' aria-hidden='true'>{html.escape(_initials(org_name))}</div><div><h1>{org_name}</h1><p>Personnel Training &amp; Compliance Record</p></div><span class='verified'>✓ VERIFIED</span></header>
<section class='identity'><div class='avatar' role='img' aria-label='Personnel photograph unavailable; initials shown'>{html.escape(_initials(person_name))}</div><div><h2>{person_name}</h2><p>{title}</p><div class='meta'><span>Staff No: {staff}</span><span>Licence No: {licence}</span><span>Profile: {profile_state}</span></div></div><div class='qr-label'>Verification link validated<br/>Official public record</div></section>
<section class='summary' aria-label='Training compliance summary'><span class='metric'>{summary.get('current',0)} Current</span><span class='metric'>{summary.get('due_soon',0)} Due Soon</span><span class='metric'>{summary.get('overdue',0)} Overdue</span><span class='metric'>{summary.get('deferred',0)} Deferred</span></section>
<section class='next-action'>{next_block}</section>
<section class='training-shell'><table><thead><tr><th>Training</th><th>Last Completed</th><th>Next Due</th><th>Status</th><th>Evidence</th><th><span class='sr-only'>Actions</span></th></tr></thead><tbody>{''.join(table_rows)}</tbody></table><div class='cards'>{''.join(cards)}</div></section>
</main>
<script>
const closeMenus=()=>document.querySelectorAll('.row-menu[open]').forEach(x=>x.removeAttribute('open'));
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeMenus()}});
document.querySelectorAll('[data-copy]').forEach(btn=>btn.addEventListener('click',async()=>{{await navigator.clipboard?.writeText(btn.dataset.copy||'');closeMenus()}}));
document.querySelectorAll('[data-action-row]').forEach(row=>{{
 row.addEventListener('contextmenu',e=>{{e.preventDefault();closeMenus();row.querySelector('.row-menu')?.setAttribute('open','')}});
 let timer; row.addEventListener('pointerdown',e=>{{if(e.pointerType!=='mouse')timer=setTimeout(()=>{{closeMenus();row.querySelector('.row-menu')?.setAttribute('open','')}},650)}});
 ['pointerup','pointercancel','pointermove'].forEach(name=>row.addEventListener(name,()=>clearTimeout(timer)));
}});
</script>
"""
    return HTMLResponse(content=f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{person_name} · Training verification</title><style>{css}</style></head><body>{body}</body></html>")


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self._saved_pages = []
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#667085"))
            self.drawString(14 * mm, 9 * mm, "Controlled Training Record")
            self.drawCentredString(A4[0] / 2, 9 * mm, "QAM/49A Rev 00")
            self.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {self._pageNumber} of {page_count}")
            super().showPage()
        super().save()


def _compact_pdf_builder(original_builder, *args, **kwargs) -> bytes:
    try:
        user = kwargs["user"]
        amo = kwargs.get("amo")
        logo_path = kwargs.get("logo_path")
        status_items = kwargs.get("status_items") or []
        records = kwargs.get("records") or []
        course_by_id = kwargs.get("course_by_id") or {}
        upcoming_events = kwargs.get("upcoming_events") or []
        verification_url = kwargs.get("verification_url")
        report_settings = kwargs.get("report_settings") or {}
    except Exception:
        return original_builder(*args, **kwargs)

    # The QR must never encode a relative path. Preserve the report rather than
    # silently placing a broken QR if a legacy caller did not supply a URL.
    if not verification_url or urlsplit(str(verification_url)).scheme != "https" or not urlsplit(str(verification_url)).netloc:
        raise RuntimeError("Training record PDF requires an absolute HTTPS verification URL.")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=13*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("BodyCompact", parent=styles["BodyText"], fontSize=7.6, leading=9.2, spaceAfter=0)
    small = ParagraphStyle("Small", parent=body, fontSize=6.8, leading=8, textColor=colors.HexColor("#667085"))
    title_style = ParagraphStyle("TitleCompact", parent=styles["Heading1"], fontSize=12, leading=14, spaceAfter=2, textColor=colors.HexColor("#17212b"))
    accent = colors.HexColor("#8a6f20")
    story: list[Any] = []

    logo = None
    if logo_path:
        try:
            logo = Image(logo_path, width=26*mm, height=12*mm, kind="proportional")
        except Exception:
            logo = None
    masthead_left = logo or Paragraph(html.escape(str(getattr(amo, "name", None) or "AMO")), title_style)
    masthead = Table([[masthead_left, Paragraph(f"<b>{html.escape(str(getattr(amo,'name',None) or 'Approved Maintenance Organisation'))}</b><br/><b>INDIVIDUAL TRAINING &amp; COMPLIANCE RECORD</b>", body), Paragraph("<b>QAM/49A</b><br/>Rev 00", body)]], colWidths=[30*mm, 118*mm, 28*mm])
    masthead.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,0),(-1,-1),1.2,accent),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.extend([masthead, Spacer(1,3*mm)])

    name = str(getattr(user,"full_name",None) or f"{getattr(user,'first_name','')} {getattr(user,'last_name','')}").strip()
    initials = _initials(name)
    avatar = Table([[Paragraph(f"<b>{html.escape(initials)}</b>", title_style)]], colWidths=[18*mm], rowHeights=[22*mm])
    avatar.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f2f4f7")),("BOX",(0,0),(-1,-1),.5,colors.HexColor("#d0d5dd")),("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    qr_drawing = None
    try:
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing
        widget = qr.QrCodeWidget(str(verification_url)); bounds=widget.getBounds(); size=22*mm
        qr_drawing=Drawing(size,size,transform=[size/(bounds[2]-bounds[0]),0,0,size/(bounds[3]-bounds[1]),0,0]); qr_drawing.add(widget)
    except Exception:
        qr_drawing = Paragraph("Verify online", small)
    identity_text = Paragraph(f"<b>{html.escape(name)}</b><br/>{html.escape(str(getattr(user,'position_title',None) or 'Personnel'))}<br/>Staff No: {html.escape(str(getattr(user,'staff_code',None) or '—'))}<br/>Licence: {html.escape(str(getattr(user,'licence_number',None) or '—'))}", body)
    generated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    reference = str(getattr(user,"id","") or "")[-8:].upper()
    verify_cell = Table([[qr_drawing],[Paragraph(f"Verify online<br/>Generated: {generated}<br/>Record reference: {html.escape(reference)}",small)]], colWidths=[42*mm])
    verify_cell.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    identity = Table([[avatar, identity_text, verify_cell]], colWidths=[22*mm,112*mm,42*mm])
    identity.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.extend([identity, Spacer(1,2.5*mm)])

    counts=defaultdict(int)
    for item in status_items:
        counts[str(getattr(item,"status","") or "").upper()]+=1
    band = Table([[f"{counts['OK']} Current", f"{counts['DUE_SOON']} Due Soon", f"{counts['OVERDUE']} Overdue", f"{counts['DEFERRED']} Deferred"]], colWidths=[44*mm]*4)
    band.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f8fafc")),("BOX",(0,0),(-1,-1),.5,colors.HexColor("#d0d5dd")),("ALIGN",(0,0),(-1,-1),"CENTER"),("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.extend([band, Spacer(1,2.5*mm)])

    item_by_code={str(getattr(item,"course_id",'')):item for item in status_items}
    table_data=[[Paragraph("<b>Training</b>",small),Paragraph("<b>Completed</b>",small),Paragraph("<b>Next Due</b>",small),Paragraph("<b>Scheduled</b>",small),Paragraph("<b>Status</b>",small)]]
    for item in sorted(status_items,key=lambda x:({"OVERDUE":0,"DUE_SOON":1,"DEFERRED":2}.get(str(getattr(x,'status','')).upper(),5),str(getattr(x,'course_name','')).casefold())):
        code=str(getattr(item,"course_id","") or ""); course=next((c for c in course_by_id.values() if str(getattr(c,'course_id',''))==code),None)
        kind=training_type_label(getattr(course,"kind",None)) if course else "—"
        status=_STATUS_LABELS.get(str(getattr(item,"status","") or "").upper(),str(getattr(item,"status","") or "").replace("_"," ").title())
        if course and status=="Current" and is_initial_course_explicit(course) and not getattr(course,"frequency_months",None): status="Completed"
        next_due=getattr(item,"extended_due_date",None) or getattr(item,"valid_until",None)
        table_data.append([
            Paragraph(f"<b>{html.escape(str(getattr(item,'course_name','Training')))}</b><br/><font color='#667085'>{html.escape(code)} · {kind}</font>",body),
            Paragraph(_pdf_date(getattr(item,"last_completion_date",None)),body),
            Paragraph(_pdf_date(next_due),body),
            Paragraph(_pdf_date(getattr(item,"upcoming_event_date",None)),body),
            Paragraph(html.escape(status),body),
        ])
    training_table=Table(table_data,colWidths=[75*mm,27*mm,27*mm,27*mm,22*mm],repeatRows=1)
    training_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
    story.append(training_table)

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


def _pdf_date(value: Any) -> str:
    if not value:
        return "—"
    if hasattr(value,"strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def install_training_record_presentation(router_module) -> None:
    """Install the corrected shared Training record presentation hooks."""

    original_payload = router_module._public_training_profile_payload
    original_pdf_builder = router_module._build_training_user_record_pdf_bytes

    def public_payload(db, *, amo_id: str, user_id: str, record_id: Optional[str] = None):
        return _augment_public_payload(original_payload, db, amo_id=amo_id, user_id=user_id, record_id=record_id)

    def verification_url(*, user_id: str, amo=None, db=None, report_token: Optional[str] = None):
        return absolute_training_verification_url(db=db, user_id=user_id, amo=amo, report_token=report_token)

    def pdf_builder(*args, **kwargs):
        return _compact_pdf_builder(original_pdf_builder, *args, **kwargs)

    router_module._public_training_profile_payload = public_payload
    router_module._training_profile_html = _training_profile_html
    router_module._training_profile_verification_url = verification_url
    router_module._build_training_user_record_pdf_bytes = pdf_builder

    # Replace only legacy classification helpers. The canonical policy evaluator
    # remains the single status/date source for API, public view and PDF.
    training_compliance.is_initial_course = is_initial_course_explicit
    training_compliance.is_refresher_course = is_recurrent_course_explicit


__all__ = [
    "absolute_training_verification_url",
    "canonical_public_origin",
    "explicit_recurrence_key",
    "install_training_record_presentation",
    "mask_public_email",
    "mask_public_identifier",
    "mask_public_phone",
    "normalized_training_kind",
    "training_type_label",
]
