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
from . import course_lifecycle as training_course_lifecycle
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
    return training_course_lifecycle.normalized_training_kind(value)


def training_type_label(value: Any) -> str:
    kind = normalized_training_kind(value)
    if kind == "INITIAL":
        return "Initial"
    if kind == "RECURRENT":
        return "Recurrent"
    return "—"


def is_initial_course_explicit(course: training_models.TrainingCourse) -> bool:
    return training_course_lifecycle.is_initial_course(course)


def is_recurrent_course_explicit(course: training_models.TrainingCourse) -> bool:
    return training_course_lifecycle.is_recurrent_course(course)


def explicit_recurrence_key(course: training_models.TrainingCourse, courses: Iterable[training_models.TrainingCourse] = ()) -> str:
    return training_course_lifecycle.explicit_recurrence_key(course, courses)


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
    for env_name in ("APP_PUBLIC_BASE_URL", "PLATFORM_API_BASE_URL", "PUBLIC_APP_URL", "PLATFORM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL"):
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
        group_records.sort(key=lambda record: (record.completion_date or date.min, str(record.created_at or "")), reverse=True)
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
                "hours": getattr(record, "hours_completed", None),
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

    legacy_records = list(payload.get("records") or [])
    rows = _build_requirement_rows(db, amo_id=amo_id, user=user)
    if record_id:
        rows = [
            row for row in rows
            if any(str(history.get("record_id")) == str(record_id) for history in row.get("history") or [])
        ]
        if not rows:
            selected = next((entry for entry in legacy_records if str(entry.get("record_id")) == str(record_id)), None)
            if selected is not None:
                rows = [{
                    "requirement_key": f"record:{record_id}",
                    "course_pk": None,
                    "course_id": str(selected.get("course_id") or ""),
                    "course_name": str(selected.get("course_name") or "Training record"),
                    "course_type": "Training",
                    "last_completed": selected.get("completion_date"),
                    "next_due": selected.get("valid_until"),
                    "scheduled": None,
                    "compliance_status": "Completed",
                    "evidence_available": False,
                    "record_count": 1,
                    "history": [{
                        "record_id": str(record_id),
                        "type": "Training",
                        "course_code": selected.get("course_id"),
                        "completed": selected.get("completion_date"),
                        "next_due": selected.get("valid_until"),
                        "hours": None,
                        "score": None,
                        "certificate_reference": selected.get("certificate_reference"),
                        "evidence_available": False,
                        "verification_status": selected.get("verification_status"),
                    }],
                }]
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
    tenant.setdefault("contact_email", getattr(user.amo, "contact_email", None) if getattr(user, "amo", None) else None)
    tenant.setdefault("contact_phone", getattr(user.amo, "contact_phone", None) if getattr(user, "amo", None) else None)
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

    org_name_raw = str(tenant.get("name") or tenant.get("organisation_name") or "Approved Maintenance Organisation")
    person_name_raw = str(user.get("full_name") or user.get("name") or "Personnel record")
    title_raw = str(user.get("position_title") or user.get("job_title") or user.get("position") or "Personnel")
    org_name = html.escape(org_name_raw)
    person_name = html.escape(person_name_raw)
    title = html.escape(title_raw)
    profile_state = "Active" if user.get("is_active", True) else "Inactive"

    accent = str(tenant.get("brand_accent") or "#8a6f20")
    if not accent.startswith("#") or len(accent) not in (4, 7):
        accent = "#8a6f20"

    def safe_image_url(*values: Any) -> Optional[str]:
        for value in values:
            raw = str(value or "").strip()
            if not raw:
                continue
            if raw.startswith("/"):
                return html.escape(raw, quote=True)
            parsed = urlsplit(raw)
            if parsed.scheme.lower() == "https" and parsed.netloc:
                return html.escape(raw, quote=True)
        return None

    logo_url = safe_image_url(
        tenant.get("logo_url"),
        tenant.get("brand_logo_url"),
        tenant.get("public_logo_url"),
    )
    photo_url = safe_image_url(
        user.get("photo_url"),
        user.get("profile_image_url"),
        user.get("avatar_url"),
    )

    brand_visual = (
        f"<img src='{logo_url}' alt='' width='56' height='56' decoding='async' fetchpriority='high'>"
        if logo_url
        else html.escape(_initials(org_name_raw))
    )
    avatar_visual = (
        f"<img src='{photo_url}' alt='' width='88' height='88' decoding='async' fetchpriority='high'>"
        if photo_url
        else html.escape(_initials(person_name_raw))
    )

    meta_items: list[str] = []
    staff = user.get("staff_code") or user.get("staff_no")
    licence = user.get("licence_number") or user.get("license_number")
    if staff:
        meta_items.append(f"<span class='meta-pill'>Staff {html.escape(str(staff))}</span>")
    if licence:
        meta_items.append(f"<span class='meta-pill'>Licence {html.escape(str(licence))}</span>")
    meta_items.append(f"<span class='meta-pill'>{profile_state}</span>")

    exception = next((row for row in requirements if row.get("compliance_status") == "Overdue"), None)
    next_action = ""
    if exception:
        next_action = (
            "<section class='next-action is-overdue' aria-label='Training action required'>"
            "<div class='next-icon' aria-hidden='true'>!</div>"
            "<div><span class='eyebrow'>Action required</span>"
            f"<strong>{html.escape(str(exception.get('course_name') or 'Training'))}</strong>"
            f"<span>Due {_fmt_public_date(exception.get('next_due'))}</span></div>"
            "</section>"
        )
    else:
        candidate = next((row for row in requirements if row.get("next_due")), None)
        if candidate:
            schedule = ""
            if candidate.get("scheduled"):
                schedule = f"<span>Scheduled {_fmt_public_date(candidate.get('scheduled'))}</span>"
            next_action = (
                "<section class='next-action' aria-label='Next training due'>"
                "<div class='next-icon' aria-hidden='true'>↗</div>"
                "<div><span class='eyebrow'>Next due</span>"
                f"<strong>{html.escape(str(candidate.get('course_name') or 'Training'))}</strong>"
                f"<span>{_fmt_public_date(candidate.get('next_due'))}</span>{schedule}</div>"
                "</section>"
            )

    training_rows: list[str] = []
    for row in requirements:
        name = html.escape(str(row.get("course_name") or "Training"))
        code = html.escape(str(row.get("course_id") or ""))
        course_type = html.escape(str(row.get("course_type") or "Training"))
        status_raw = str(row.get("compliance_status") or "Not completed")
        status = html.escape(status_raw)
        status_class = status_raw.lower().replace(" ", "-").replace("_", "-")
        completed = _fmt_public_date(row.get("last_completed"))
        next_due = _fmt_public_date(row.get("next_due"))

        detail_items: list[str] = []
        if row.get("scheduled"):
            detail_items.append(
                "<div class='detail-item'><span>Scheduled</span>"
                f"<strong>{_fmt_public_date(row.get('scheduled'))}</strong></div>"
            )
        if row.get("evidence_available"):
            detail_items.append(
                "<div class='detail-item'><span>Evidence</span><strong>Verified evidence on file</strong></div>"
            )

        history = list(row.get("history") or [])
        older_history = history[1:] if len(history) > 1 else []
        history_html = ""
        if older_history:
            history_items = "".join(
                "<li><div><strong>"
                f"{html.escape(str(item.get('type') or 'Training'))}</strong>"
                f"<span>{html.escape(str(item.get('course_code') or ''))}</span></div>"
                f"<time>{_fmt_public_date(item.get('completed'))}</time></li>"
                for item in older_history
            )
            history_html = f"<div class='history-block'><h4>Previous completions</h4><ul>{history_items}</ul></div>"

        details_html = ""
        if detail_items or history_html:
            details_html = (
                "<details class='row-details'>"
                "<summary><span>Details</span><svg viewBox='0 0 24 24' aria-hidden='true'><path d='m9 18 6-6-6-6'/></svg></summary>"
                f"<div class='detail-panel'>{''.join(detail_items)}{history_html}</div>"
                "</details>"
            )

        evidence_badge = (
            "<span class='evidence-badge' title='Verified evidence is recorded' aria-label='Verified evidence is recorded'>"
            "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M20 6 9 17l-5-5'/></svg></span>"
            if row.get("evidence_available")
            else ""
        )

        training_rows.append(
            "<article class='training-row'>"
            f"<div class='training-name'><strong>{name}</strong><span>{code} · {course_type}</span></div>"
            f"<div class='data-cell'><span class='data-label'>Completed</span><strong>{completed}</strong></div>"
            f"<div class='data-cell'><span class='data-label'>Next due</span><strong>{next_due}</strong></div>"
            f"<div class='status-cell'><span class='status status-{status_class}'>{status}</span>{evidence_badge}</div>"
            f"{details_html}</article>"
        )

    action_icons = """
<nav class='report-actions' aria-label='Report actions'>
  <button class='icon-button' type='button' data-share-report aria-label='Share report' title='Share'>
    <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 16V3'/><path d='m7 8 5-5 5 5'/><path d='M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7'/></svg>
  </button>
  <button class='icon-button' type='button' data-copy-link aria-label='Copy verification link' title='Copy link'>
    <svg viewBox='0 0 24 24' aria-hidden='true'><rect x='9' y='9' width='11' height='11' rx='2'/><path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/></svg>
  </button>
  <button class='icon-button' type='button' data-download-pdf aria-label='Download PDF' title='Download PDF'>
    <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/><path d='M12 12v6'/><path d='m9 15 3 3 3-3'/></svg>
  </button>
  <button class='icon-button' type='button' data-print-report aria-label='Print report' title='Print'>
    <svg viewBox='0 0 24 24' aria-hidden='true'><path d='M6 9V2h12v7'/><path d='M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2'/><rect x='6' y='14' width='12' height='8'/></svg>
  </button>
</nav>
"""

    css = f"""
:root{{--accent:{accent};--bg:#f2f2f7;--surface:rgba(255,255,255,.82);--surface-solid:#fff;--label:#1c1c1e;--secondary:#636366;--tertiary:#8e8e93;--separator:rgba(60,60,67,.14);--blue:#007aff;--green:#248a3d;--orange:#c93400;--red:#d70015;--radius-xl:28px;--radius-lg:22px;--radius-md:16px;--shadow:0 1px 2px rgba(0,0,0,.025),0 12px 34px rgba(0,0,0,.055)}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%;text-rendering:optimizeLegibility}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 12% -12%,color-mix(in srgb,var(--accent) 12%,transparent),transparent 34rem),var(--bg);color:var(--label);font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue","Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}}button{{font:inherit}}main{{width:min(1120px,100%);margin:auto;padding:max(18px,env(safe-area-inset-top)) max(18px,env(safe-area-inset-right)) max(34px,env(safe-area-inset-bottom)) max(18px,env(safe-area-inset-left))}}.mast{{display:flex;align-items:center;gap:14px;min-height:72px;margin-bottom:18px}}.brand-mark{{width:56px;height:56px;flex:0 0 56px;display:grid;place-items:center;overflow:hidden;border-radius:17px;background:linear-gradient(145deg,color-mix(in srgb,var(--accent) 82%,white),var(--accent));color:#fff;font-size:18px;font-weight:760;letter-spacing:-.03em;box-shadow:inset 0 1px rgba(255,255,255,.24),0 6px 18px rgba(0,0,0,.08)}}.brand-mark img{{width:100%;height:100%;display:block;object-fit:contain;background:#fff;padding:5px}}.mast-copy{{min-width:0;flex:1}}.mast h1{{margin:0;font-size:clamp(20px,3vw,28px);line-height:1.1;font-weight:730;letter-spacing:-.03em}}.mast p{{margin:4px 0 0;color:var(--secondary);font-size:13px}}.report-actions{{display:flex;align-items:center;gap:4px;padding:4px;border:1px solid var(--separator);border-radius:16px;background:rgba(255,255,255,.72);-webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);box-shadow:0 4px 18px rgba(0,0,0,.035)}}.icon-button{{width:44px;height:44px;display:grid;place-items:center;border:0;border-radius:12px;background:transparent;color:var(--blue);cursor:pointer;transition:background .15s ease,transform .12s ease}}.icon-button:hover{{background:rgba(0,122,255,.08)}}.icon-button:active{{transform:scale(.94);background:rgba(0,122,255,.13)}}.icon-button svg,.row-details svg,.evidence-badge svg{{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}}.identity{{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:18px;padding:20px;border:1px solid rgba(255,255,255,.72);border-radius:var(--radius-xl);background:var(--surface);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);box-shadow:var(--shadow)}}.avatar{{width:88px;height:88px;display:grid;place-items:center;overflow:hidden;border-radius:24px;background:linear-gradient(145deg,color-mix(in srgb,var(--accent) 68%,white),var(--accent));color:#fff;font-size:29px;font-weight:730;letter-spacing:-.04em;box-shadow:inset 0 0 0 1px rgba(255,255,255,.2),0 7px 20px rgba(0,0,0,.09)}}.avatar img{{width:100%;height:100%;display:block;object-fit:cover;object-position:center}}.identity-copy{{min-width:0}}.identity h2{{margin:0;font-size:clamp(23px,3vw,30px);line-height:1.08;font-weight:740;letter-spacing:-.035em}}.identity .role{{margin:5px 0 0;color:var(--secondary)}}.meta{{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}}.meta-pill{{display:inline-flex;align-items:center;min-height:28px;padding:4px 9px;border-radius:9px;background:rgba(118,118,128,.08);color:var(--secondary);font-size:12px;font-weight:580}}.verified{{display:inline-flex;align-items:center;gap:7px;align-self:flex-start;padding:8px 11px;border-radius:999px;background:rgba(52,199,89,.12);color:#16743c;font-size:12px;font-weight:720;white-space:nowrap}}.verified svg{{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}.summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}}.metric{{padding:14px 15px;border:1px solid var(--separator);border-radius:var(--radius-md);background:rgba(255,255,255,.76);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);box-shadow:0 3px 14px rgba(0,0,0,.025)}}.metric strong{{display:block;font-size:23px;line-height:1;font-weight:740;letter-spacing:-.035em}}.metric span{{display:block;margin-top:5px;color:var(--secondary);font-size:12px;font-weight:530}}.next-action{{display:flex;align-items:center;gap:13px;min-height:70px;margin-bottom:14px;padding:13px 16px;border:1px solid color-mix(in srgb,var(--accent) 20%,transparent);border-radius:var(--radius-lg);background:color-mix(in srgb,var(--accent) 7%,rgba(255,255,255,.9));box-shadow:0 4px 16px rgba(0,0,0,.025)}}.next-action.is-overdue{{border-color:rgba(215,0,21,.18);background:rgba(255,59,48,.065)}}.next-icon{{width:38px;height:38px;display:grid;place-items:center;flex:0 0 38px;border-radius:12px;background:rgba(255,255,255,.75);color:var(--accent);font-size:17px;font-weight:750}}.is-overdue .next-icon{{color:var(--red)}}.next-action>div:last-child{{display:flex;min-width:0;flex-wrap:wrap;align-items:baseline;gap:3px 10px}}.next-action .eyebrow{{width:100%;color:var(--secondary);font-size:11px;font-weight:720;letter-spacing:.055em;text-transform:uppercase}}.next-action strong{{font-size:15px;font-weight:680}}.next-action span:not(.eyebrow){{color:var(--secondary);font-size:13px}}.training-shell{{overflow:hidden;border:1px solid var(--separator);border-radius:var(--radius-xl);background:rgba(255,255,255,.82);-webkit-backdrop-filter:saturate(180%) blur(22px);backdrop-filter:saturate(180%) blur(22px);box-shadow:var(--shadow)}}.training-heading,.training-row{{display:grid;grid-template-columns:minmax(260px,1.7fr) minmax(118px,.7fr) minmax(118px,.7fr) minmax(120px,.6fr);align-items:center;gap:14px}}.training-heading{{min-height:44px;padding:0 18px;border-bottom:1px solid var(--separator);color:var(--tertiary);font-size:11px;font-weight:670;letter-spacing:.025em;text-transform:uppercase}}.training-row{{min-height:78px;padding:14px 18px}}.training-row+.training-row{{border-top:1px solid var(--separator)}}.training-row:hover{{background:rgba(118,118,128,.032)}}.training-name{{min-width:0}}.training-name strong{{display:block;overflow:hidden;text-overflow:ellipsis;font-size:15px;line-height:1.25;font-weight:660}}.training-name span{{display:block;margin-top:4px;color:var(--secondary);font-size:12px}}.data-cell{{font-variant-numeric:tabular-nums}}.data-cell strong{{font-size:14px;font-weight:590}}.data-label{{display:none}}.status-cell{{display:flex;align-items:center;gap:7px}}.status{{width:max-content;display:inline-flex;align-items:center;gap:6px;min-height:28px;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:660}}.status::before{{width:6px;height:6px;content:"";border-radius:50%;background:currentColor}}.status-current,.status-completed{{color:#16743c;background:rgba(52,199,89,.11)}}.status-due-soon{{color:#9a5b00;background:rgba(255,149,0,.12)}}.status-overdue{{color:#c62f27;background:rgba(255,59,48,.11)}}.status-deferred{{color:#755900;background:rgba(255,204,0,.14)}}.status-scheduled{{color:#235ea7;background:rgba(0,122,255,.10)}}.status-not-completed{{color:#7a2731;background:rgba(255,59,48,.08)}}.evidence-badge{{width:27px;height:27px;display:grid;place-items:center;border-radius:999px;background:rgba(52,199,89,.10);color:var(--green)}}.evidence-badge svg{{width:15px;height:15px}}.row-details{{grid-column:1/-1;margin:0}}.row-details>summary{{width:max-content;display:inline-flex;align-items:center;gap:4px;margin-top:4px;list-style:none;color:var(--blue);font-size:12px;font-weight:620;cursor:pointer}}.row-details>summary::-webkit-details-marker{{display:none}}.row-details>summary svg{{width:16px;height:16px;transition:transform .16s ease}}.row-details[open]>summary svg{{transform:rotate(90deg)}}.detail-panel{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 14px;margin-top:10px;padding:13px 15px;border-radius:var(--radius-md);background:rgba(118,118,128,.055)}}.detail-item span{{display:block;color:var(--tertiary);font-size:11px;font-weight:560}}.detail-item strong{{display:block;margin-top:3px;font-size:13px;font-weight:620}}.history-block{{grid-column:1/-1}}.history-block h4{{margin:3px 0 4px;font-size:12px}}.history-block ul{{margin:0;padding:0;list-style:none}}.history-block li{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 0;border-top:1px solid var(--separator);font-size:12px}}.history-block li div strong,.history-block li div span{{display:block}}.history-block li div span,.history-block time{{color:var(--secondary);font-weight:450}}.icon-button:focus-visible,.row-details>summary:focus-visible{{outline:3px solid rgba(0,122,255,.28);outline-offset:2px}}.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
@media(max-width:850px){{.summary{{grid-template-columns:repeat(2,minmax(0,1fr))}}.training-heading{{display:none}}.training-row{{grid-template-columns:minmax(0,1fr) auto;gap:8px 12px;padding:16px}}.training-name{{grid-column:1}}.status-cell{{grid-column:2;grid-row:1;justify-content:flex-end}}.data-cell{{display:grid;grid-template-columns:92px minmax(0,1fr);grid-column:1/-1;padding-top:3px}}.data-label{{display:inline;color:var(--tertiary);font-size:12px;font-weight:450}}.row-details{{grid-column:1/-1}}}}
@media(max-width:600px){{main{{padding:max(12px,env(safe-area-inset-top)) max(12px,env(safe-area-inset-right)) max(26px,env(safe-area-inset-bottom)) max(12px,env(safe-area-inset-left))}}.mast{{align-items:flex-start;flex-wrap:wrap}}.brand-mark{{width:48px;height:48px;flex-basis:48px;border-radius:14px}}.mast-copy{{width:calc(100% - 64px)}}.mast h1{{font-size:21px}}.report-actions{{width:100%;justify-content:space-between;margin-top:2px}}.report-actions .icon-button{{flex:1}}.identity{{grid-template-columns:auto minmax(0,1fr);gap:13px;padding:16px;border-radius:24px}}.avatar{{width:64px;height:64px;border-radius:18px;font-size:21px}}.verified{{grid-column:1/-1;justify-self:start}}.identity h2{{font-size:21px}}.summary{{gap:8px}}.metric{{padding:12px}}.metric strong{{font-size:20px}}.next-action{{align-items:flex-start;padding:14px}}.training-shell{{border-radius:24px}}.status{{font-size:11px}}.detail-panel{{grid-template-columns:1fr}}.history-block{{grid-column:1}}}}
@media print{{body{{background:#fff}}main{{width:100%;max-width:none;padding:0}}.report-actions{{display:none}}.identity,.metric,.training-shell{{background:#fff;box-shadow:none;-webkit-backdrop-filter:none;backdrop-filter:none}}.training-row{{break-inside:avoid}}.row-details:not([open]){{display:none}}}}
"""

    body = f"""
<main>
<header class='mast'>
  <div class='brand-mark' aria-hidden='true'>{brand_visual}</div>
  <div class='mast-copy'><h1>{org_name}</h1><p>Personnel Training &amp; Compliance Record</p></div>
  {action_icons}
</header>
<section class='identity'>
  <div class='avatar' role='img' aria-label='Personnel image'>{avatar_visual}</div>
  <div class='identity-copy'><h2>{person_name}</h2><p class='role'>{title}</p><div class='meta'>{''.join(meta_items)}</div></div>
  <span class='verified'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M20 6 9 17l-5-5'/></svg>Verified</span>
</section>
<section class='summary' aria-label='Training compliance summary'>
  <div class='metric'><strong>{summary.get('current',0)}</strong><span>Current</span></div>
  <div class='metric'><strong>{summary.get('due_soon',0)}</strong><span>Due soon</span></div>
  <div class='metric'><strong>{summary.get('overdue',0)}</strong><span>Overdue</span></div>
  <div class='metric'><strong>{summary.get('deferred',0)}</strong><span>Deferred</span></div>
</section>
{next_action}
<section class='training-shell' aria-label='Training requirements'>
  <div class='training-heading' aria-hidden='true'><span>Training</span><span>Completed</span><span>Next due</span><span>Status</span></div>
  {''.join(training_rows)}
</section>
<p id='action-feedback' class='sr-only' aria-live='polite'></p>
</main>
<script>
const feedback=document.getElementById('action-feedback');
const say=(message)=>{{if(feedback)feedback.textContent=message;}};
const currentUrl=()=>window.location.href;
const copyCurrentUrl=async()=>{{
  try{{await navigator.clipboard.writeText(currentUrl());say('Verification link copied.');}}
  catch{{say('Unable to copy the verification link.');}}
}};
document.querySelector('[data-copy-link]')?.addEventListener('click',copyCurrentUrl);
document.querySelector('[data-share-report]')?.addEventListener('click',async()=>{{
  const data={{title:document.title,text:'Verified personnel training record',url:currentUrl()}};
  if(navigator.share){{
    try{{await navigator.share(data);return;}}
    catch(error){{if(error?.name==='AbortError')return;}}
  }}
  await copyCurrentUrl();
}});
document.querySelector('[data-download-pdf]')?.addEventListener('click',()=>{{
  const pdfUrl=new URL(currentUrl());pdfUrl.searchParams.set('format','pdf');window.location.assign(pdfUrl.toString());
}});
document.querySelector('[data-print-report]')?.addEventListener('click',()=>window.print());
</script>
"""
    return HTMLResponse(content=f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><meta name='color-scheme' content='light'><meta name='theme-color' content='{accent}'><title>{person_name} · Training verification</title><style>{css}</style></head><body>{body}</body></html>")


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, training_pdf_meta=None, **kwargs):
        self._saved_pages = []
        self._training_pdf_meta = training_pdf_meta or {}
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            meta = self._training_pdf_meta or {}
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#667085"))
            self.drawString(14 * mm, 9 * mm, str(meta.get("footer_note") or "Controlled Training Record")[:88])
            form_no = str(meta.get("form_no") or "QAM/49A")
            revision = str(meta.get("revision") or "00")
            self.drawCentredString(A4[0] / 2, 9 * mm, f"{form_no} Rev {revision}")
            self.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {self._pageNumber} of {page_count}")
            super().showPage()
        super().save()


def _numbered_canvas_maker(meta: dict[str, Any]):
    def maker(*args, **kwargs):
        return _NumberedCanvas(*args, training_pdf_meta=meta, **kwargs)
    return maker


def _group_pdf_status_items(status_items: list[Any], course_by_id: dict[str, Any]) -> list[Any]:
    courses = list(course_by_id.values())
    grouped: dict[str, tuple[Any, Any]] = {}
    for item in status_items:
        code = str(getattr(item, "course_id", "") or "")
        course = next((candidate for candidate in courses if str(getattr(candidate, "course_id", "")) == code or str(getattr(candidate, "id", "")) == code), None)
        key = explicit_recurrence_key(course, courses) if course is not None else f"item:{code}"
        current = grouped.get(key)
        current_course = current[1] if current else None
        candidate_rank = 2 if course is not None and is_recurrent_course_explicit(course) else 1 if course is not None and is_initial_course_explicit(course) else 0
        current_rank = 2 if current_course is not None and is_recurrent_course_explicit(current_course) else 1 if current_course is not None and is_initial_course_explicit(current_course) else 0
        if current is None or candidate_rank > current_rank:
            grouped[key] = (item, course)
    return [entry[0] for entry in grouped.values()]


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
        deferrals = kwargs.get("deferrals") or []
        status_items = _group_pdf_status_items(status_items, course_by_id)
    except Exception:
        return original_builder(*args, **kwargs)

    # The QR must never encode a relative path. Preserve the report rather than
    # silently placing a broken QR if a legacy caller did not supply a URL.
    if not verification_url or urlsplit(str(verification_url)).scheme != "https" or not urlsplit(str(verification_url)).netloc:
        raise RuntimeError("Training record PDF requires an absolute HTTPS verification URL.")

    show_compliance_summary = report_settings.get("show_compliance_summary", True) is not False
    show_training_history = report_settings.get("show_training_history", True) is not False
    show_scheduled_events = report_settings.get("show_scheduled_events", True) is not False
    show_deferrals = report_settings.get("show_deferrals", True) is not False
    report_title = str(report_settings.get("title") or "Individual Training & Compliance Record")
    report_subtitle = str(report_settings.get("subtitle") or "")
    form_no = str(report_settings.get("form_no") or "QAM/49A")
    issue_date = str(report_settings.get("issue_date") or "")
    revision = str(report_settings.get("revision") or "00")
    footer_note = str(report_settings.get("footer_note") or "Controlled Training Record")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=13*mm, bottomMargin=16*mm, title=report_title)
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
    masthead_title = html.escape(report_title.upper())
    masthead_meta = f"<b>{html.escape(form_no)}</b><br/>Rev {html.escape(revision)}" + (f"<br/>{html.escape(issue_date)}" if issue_date else "")
    masthead = Table([[masthead_left, Paragraph(f"<b>{html.escape(str(getattr(amo,'name',None) or 'Approved Maintenance Organisation'))}</b><br/><b>{masthead_title}</b>" + (f"<br/><font color='#667085'>{html.escape(report_subtitle)}</font>" if report_subtitle else ""), body), Paragraph(masthead_meta, body)]], colWidths=[30*mm, 118*mm, 28*mm])
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
    if show_compliance_summary:
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

    if show_training_history and records:
        history_data = [[Paragraph("<b>Course</b>", small), Paragraph("<b>Completed</b>", small), Paragraph("<b>Valid until</b>", small), Paragraph("<b>Certificate</b>", small)]]
        for record in sorted(records, key=lambda row: (getattr(row, "completion_date", None) or date.min, str(getattr(row, "created_at", ""))), reverse=True):
            course = course_by_id.get(str(getattr(record, "course_id", "")))
            history_data.append([
                Paragraph(html.escape(str(getattr(course, "course_name", None) or getattr(record, "course_id", "Training"))), body),
                Paragraph(_pdf_date(getattr(record, "completion_date", None)), body),
                Paragraph(_pdf_date(getattr(record, "valid_until", None)), body),
                Paragraph(html.escape(str(getattr(record, "certificate_reference", None) or "—")), body),
            ])
        history_table = Table(history_data, colWidths=[86*mm, 30*mm, 30*mm, 32*mm], repeatRows=1)
        history_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),6.8)]))
        story.extend([Spacer(1,2.5*mm), Paragraph("<b>Training record log</b>", body), history_table])

    if show_scheduled_events and upcoming_events:
        event_data = [[Paragraph("<b>Scheduled training</b>", small), Paragraph("<b>Starts</b>", small), Paragraph("<b>Status</b>", small)]]
        for event in sorted(upcoming_events, key=lambda row: (getattr(row, "starts_on", None) or date.max, str(getattr(row, "title", "")) )):
            course = course_by_id.get(str(getattr(event, "course_id", "")))
            event_data.append([
                Paragraph(html.escape(str(getattr(event, "title", None) or getattr(course, "course_name", None) or "Training event")), body),
                Paragraph(_pdf_date(getattr(event, "starts_on", None)), body),
                Paragraph(html.escape(str(getattr(getattr(event, "status", None), "value", getattr(event, "status", None)) or "—")), body),
            ])
        event_table = Table(event_data, colWidths=[108*mm, 34*mm, 36*mm], repeatRows=1)
        event_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.extend([Spacer(1,2.5*mm), Paragraph("<b>Scheduled training and events</b>", body), event_table])

    if show_deferrals and deferrals:
        deferral_data = [[Paragraph("<b>Course</b>", small), Paragraph("<b>Original due</b>", small), Paragraph("<b>Extended due</b>", small), Paragraph("<b>Status</b>", small)]]
        for item in deferrals:
            course = course_by_id.get(str(getattr(item, "course_id", "")))
            deferral_data.append([
                Paragraph(html.escape(str(getattr(course, "course_name", None) or getattr(item, "course_id", "Training"))), body),
                Paragraph(_pdf_date(getattr(item, "original_due_date", None)), body),
                Paragraph(_pdf_date(getattr(item, "requested_new_due_date", None)), body),
                Paragraph(html.escape(str(getattr(getattr(item, "status", None), "value", getattr(item, "status", None)) or "—")), body),
            ])
        deferral_table = Table(deferral_data, colWidths=[76*mm, 34*mm, 34*mm, 34*mm], repeatRows=1)
        deferral_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f2f4f7")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#d0d5dd")),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.extend([Spacer(1,2.5*mm), Paragraph("<b>Deferral and extension history</b>", body), deferral_table])

    doc.build(story, canvasmaker=_numbered_canvas_maker({"form_no": form_no, "revision": revision, "footer_note": footer_note}))
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
