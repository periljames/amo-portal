"""Stable Training integration boundary for QMS and DMS.

Cross-module consumers must not independently guess whether a record is
current.  This module owns the shared lifecycle, verification, and expiry
rules used by Quality privilege checks, dashboards, and Document Control
release links.

QMS People competence reuses Training's ``evaluate_user_training_policy`` /
requirement / role-rule resolution — the same path Training people-compliance
uses for Quality-department QMS gaps. Do not invent parallel course aliases.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, noload

from . import course_lifecycle
from . import models
from . import record_lifecycle


_PASS_OUTCOMES = {"PASS", "COMPETENT", "SATISFACTORY"}
_HISTORICAL_RECORD_STATUSES = {"RENEWED", "SUPERSEDED", "INACTIVE"}
_POLICY_CURRENT_STATUSES = {"OK", "DUE_SOON", "DEFERRED"}

# Canonical QMS auditor competence course codes (Training course_id / pill labels).
QMS_INIT = "QMS-INIT"
QMS_REF = "QMS-REF"
QMS_ADMIN = "QMS-ADMIN"
QMS_CURRENCY_CODES = (QMS_INIT, QMS_REF)
QMS_COMPETENCE_CODES = (QMS_INIT, QMS_REF, QMS_ADMIN)

# Training catalogue markers that already identify the QMS family (not aliases).
_QMS_GROUP_CODE = "QMS"
_QMS_CATEGORY = "QUALITY_SYSTEMS"


def enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _normalize_codes(codes: Iterable[str]) -> list[str]:
    return sorted({str(code or "").strip().upper() for code in codes if str(code or "").strip()})


def _normalize_course_id_punctuation(value: Any) -> str:
    """Normalise course_id punctuation only (QMS_REF / 'QMS REF' → QMS-REF)."""

    text = str(value or "").strip().upper()
    if not text:
        return ""
    return "-".join(part for part in text.replace("_", "-").replace(" ", "-").split("-") if part)


def canonicalize_qms_competence_code(
    course: Any,
    *,
    requested: Iterable[str] | None = None,
) -> str | None:
    """Map a Training catalogue course onto a QMS competence pill code.

    Uses only Training's own identity fields:
    - exact / punctuation-normalised ``course_id``
    - explicit ``group_code == QMS`` + training kind
    - ``category == QUALITY_SYSTEMS`` + training kind

    No compact alias dictionaries or course-name heuristics.
    """

    wanted = set(_normalize_codes(requested or QMS_COMPETENCE_CODES))
    raw_code = str(getattr(course, "course_id", "") or "").strip().upper()
    if raw_code in wanted:
        return raw_code
    punctuated = _normalize_course_id_punctuation(raw_code)
    if punctuated in wanted:
        return punctuated

    group = str(getattr(course, "group_code", "") or "").strip().upper()
    category = enum_text(getattr(course, "category", None))
    is_qms_family = group == _QMS_GROUP_CODE or category == _QMS_CATEGORY
    if not is_qms_family:
        return None

    kind = course_lifecycle.training_kind_for_course(course)
    if kind == "INITIAL" and QMS_INIT in wanted:
        return QMS_INIT
    if kind == "RECURRENT" and QMS_REF in wanted:
        return QMS_REF
    return None


def _training_person_user_ids(db: Session, *, amo_id: str, user_id: str) -> list[str]:
    """Return the same person key Training compliance uses (portal user id)."""

    primary = str(user_id or "").strip()
    return [primary] if primary else []


def _resolve_qms_course_ids(
    db: Session,
    *,
    amo_id: str,
    codes: list[str],
) -> dict[str, list[str]]:
    """Return canonical code → TrainingCourse PK ids for this tenant."""

    wanted = _normalize_codes(codes)
    if not wanted:
        return {}
    courses = (
        db.query(models.TrainingCourse)
        .options(noload("*"))
        .filter(models.TrainingCourse.amo_id == amo_id)
        .all()
    )
    by_code: dict[str, list[str]] = {code: [] for code in wanted}
    for item in courses:
        course = item[1] if isinstance(item, tuple) and len(item) == 2 else item
        if course is None:
            continue
        canonical = canonicalize_qms_competence_code(course, requested=wanted)
        if not canonical:
            continue
        course_pk = str(getattr(course, "id", "") or "").strip()
        if not course_pk:
            continue
        by_code.setdefault(canonical, []).append(course_pk)
    return {code: ids for code, ids in by_code.items() if ids}


def _record_payload(code: str, record: Any, course: Any, *, record_status: str) -> dict[str, Any]:
    return {
        "record_id": str(record.id),
        "course_id": str(course.id),
        "course_code": code,
        "course_name": getattr(course, "course_name", None),
        "source_course_code": str(getattr(course, "course_id", "") or "").strip().upper() or None,
        "completion_date": record.completion_date.isoformat() if record.completion_date else None,
        "valid_until": record.valid_until.isoformat() if record.valid_until else None,
        "verification_status": enum_text(record.verification_status),
        "record_status": record_status,
        "source_route": f"/training/records/{record.id}",
    }


def _latest_records_by_code(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    codes: list[str],
    as_of: date,
    current_only: bool,
    verified_only: bool = True,
    active_only: bool = True,
) -> dict[str, tuple[Any, Any]]:
    """Resolve records for explicit competence codes via Training catalogue PKs.

    Prefer ``qms_auditor_competence_evidence`` / policy evaluation for People pills.
    This helper remains for AND-list evidence checks that already know the codes.
    """

    wanted = _normalize_codes(codes)
    if not wanted:
        return {}

    person_ids = _training_person_user_ids(db, amo_id=amo_id, user_id=user_id)
    resolved = _resolve_qms_course_ids(db, amo_id=amo_id, codes=wanted)
    course_pks = [pk for ids in resolved.values() for pk in ids]
    if not course_pks or not person_ids:
        return {}

    filters = [
        models.TrainingRecord.amo_id == amo_id,
        models.TrainingRecord.user_id.in_(person_ids),
        models.TrainingCourse.amo_id == amo_id,
        models.TrainingRecord.course_id.in_(course_pks),
    ]
    if active_only:
        filters.append(record_lifecycle.active_records_filter(models.TrainingRecord))
    if verified_only:
        filters.append(
            models.TrainingRecord.verification_status == models.TrainingRecordVerificationStatus.VERIFIED
        )
    if current_only:
        filters.append(or_(models.TrainingRecord.valid_until.is_(None), models.TrainingRecord.valid_until >= as_of))
    rows = (
        db.query(models.TrainingRecord, models.TrainingCourse)
        .join(models.TrainingCourse, models.TrainingCourse.id == models.TrainingRecord.course_id)
        .options(noload("*"))
        .filter(*filters)
        .order_by(
            case(
                (models.TrainingRecord.verification_status == models.TrainingRecordVerificationStatus.VERIFIED, 0),
                else_=1,
            ).asc(),
            models.TrainingRecord.valid_until.desc().nullslast(),
            models.TrainingRecord.completion_date.desc().nullslast(),
            models.TrainingRecord.created_at.desc().nullslast(),
            models.TrainingRecord.id.desc(),
        )
        .limit(max(250, len(wanted) * 8))
        .all()
    )
    by_code: dict[str, tuple[Any, Any]] = {}
    for record, course in rows:
        canonical = canonicalize_qms_competence_code(course, requested=wanted)
        if not canonical or canonical not in wanted:
            continue
        by_code.setdefault(canonical, (record, course))
    return by_code


def _latest_verified_records_by_code(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    codes: list[str],
    as_of: date,
    current_only: bool,
) -> dict[str, tuple[Any, Any]]:
    return _latest_records_by_code(
        db,
        amo_id=amo_id,
        user_id=user_id,
        codes=codes,
        as_of=as_of,
        current_only=current_only,
        verified_only=True,
    )


def _days_until(valid_until: date | None, *, as_of: date) -> int | None:
    if valid_until is None:
        return None
    return (valid_until - as_of).days


def _tracked_record_payload(code: str, record: Any, course: Any, *, as_of: date) -> dict[str, Any]:
    status = training_record_status_snapshot(record, as_of=as_of)
    payload = _record_payload(code, record, course, record_status=status)
    payload["days_until_expiry"] = _days_until(getattr(record, "valid_until", None), as_of=as_of)
    return payload


def training_record_status_snapshot(row: Any, *, as_of: date | None = None) -> str:
    """Return the DMS release status for one Training record projection."""

    as_of = as_of or date.today()
    lifecycle = enum_text(row.get("record_status") if hasattr(row, "get") else getattr(row, "record_status", None)) or "ACTIVE"
    source_lifecycle = enum_text(row.get("source_status") if hasattr(row, "get") else getattr(row, "source_status", None)) or "ACTIVE"
    verification = enum_text(row.get("verification_status") if hasattr(row, "get") else getattr(row, "verification_status", None))
    valid_until = row.get("valid_until") if hasattr(row, "get") else getattr(row, "valid_until", None)

    if lifecycle in _HISTORICAL_RECORD_STATUSES or source_lifecycle in _HISTORICAL_RECORD_STATUSES:
        return "SUPERSEDED"
    if verification == "REJECTED":
        return "REJECTED"
    if verification != "VERIFIED":
        return "PENDING"
    if valid_until is not None and valid_until < as_of:
        return "EXPIRED"
    return "READY"


def training_source_status_snapshot(
    table_name: str,
    row: Any,
    *,
    fallback: str,
    as_of: date | None = None,
) -> str:
    """Translate canonical Training rows into DMS workflow semantics."""

    table = str(table_name or "").lower()
    fallback_status = enum_text(fallback)
    if table == "training_records":
        return training_record_status_snapshot(row, as_of=as_of)
    if table == "training_certificate_issues":
        return "READY" if fallback_status == "VALID" else fallback_status or "PENDING"
    if table == "training_attendance_windows":
        return "COMPLETED" if fallback_status == "CERTIFIED" else fallback_status or "PENDING"
    if table == "training_assessment_instances":
        outcome = enum_text(row.get("outcome") if hasattr(row, "get") else getattr(row, "outcome", None))
        if fallback_status == "APPROVED" and outcome in _PASS_OUTCOMES:
            return "READY"
        return fallback_status or "PENDING"
    if table == "training_authorization_cases":
        decision = enum_text(row.get("decision") if hasattr(row, "get") else getattr(row, "decision", None))
        if decision == "APPROVED" or fallback_status == "APPROVED":
            return "READY"
        return decision or fallback_status or "PENDING"
    return fallback_status or "UNVERIFIED"


def current_training_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    required_codes: Iterable[str],
    as_of: date,
) -> dict[str, Any]:
    """Return verified, active and current evidence for QMS decisions.

    All listed codes must be current (AND). Prefer
    ``current_training_evidence_with_alternatives`` when codes are alternatives.
    """

    required = _normalize_codes(required_codes)
    if not required:
        return {"required": [], "satisfied": [], "missing": [], "records": [], "passed": True, "expired": []}

    current_by_code = _latest_verified_records_by_code(
        db, amo_id=amo_id, user_id=user_id, codes=required, as_of=as_of, current_only=True,
    )
    latest_any = _latest_verified_records_by_code(
        db, amo_id=amo_id, user_id=user_id, codes=required, as_of=as_of, current_only=False,
    )
    satisfied = sorted(current_by_code)
    missing = [code for code in required if code not in current_by_code]
    expired = [
        code
        for code in required
        if code not in current_by_code
        and code in latest_any
        and latest_any[code][0].valid_until is not None
        and latest_any[code][0].valid_until < as_of
    ]
    records = [
        _record_payload(code, record, course, record_status="READY")
        for code, (record, course) in sorted(current_by_code.items())
    ]
    return {
        "required": required,
        "satisfied": satisfied,
        "missing": missing,
        "expired": expired,
        "records": records,
        "passed": not missing,
    }


def current_training_evidence_with_alternatives(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    alternative_groups: Iterable[Iterable[str]],
    as_of: date,
) -> dict[str, Any]:
    """Return evidence where any alternative group may fully satisfy the requirement.

    Within a group every code must be current (AND). Across groups, one success
    is enough (OR). Empty ``alternative_groups`` passes (no training required).
    """

    groups = [_normalize_codes(group) for group in alternative_groups]
    groups = [group for group in groups if group]
    if not groups:
        return {
            "required": [],
            "satisfied": [],
            "missing": [],
            "expired": [],
            "records": [],
            "passed": True,
            "alternative_groups": [],
            "satisfied_group": None,
        }

    all_codes = _normalize_codes(code for group in groups for code in group)
    current_by_code = _latest_verified_records_by_code(
        db, amo_id=amo_id, user_id=user_id, codes=all_codes, as_of=as_of, current_only=True,
    )
    latest_any = _latest_verified_records_by_code(
        db, amo_id=amo_id, user_id=user_id, codes=all_codes, as_of=as_of, current_only=False,
    )
    satisfied = sorted(current_by_code)
    expired = [
        code
        for code in all_codes
        if code not in current_by_code
        and code in latest_any
        and latest_any[code][0].valid_until is not None
        and latest_any[code][0].valid_until < as_of
    ]
    satisfied_group: list[str] | None = None
    for group in groups:
        if all(code in current_by_code for code in group):
            satisfied_group = group
            break
    missing = [] if satisfied_group is not None else [code for group in groups for code in group if code not in current_by_code]
    # De-dupe missing while preserving order of first appearance across groups.
    seen: set[str] = set()
    missing_unique = []
    for code in missing:
        if code not in seen:
            seen.add(code)
            missing_unique.append(code)
    records = [
        _record_payload(code, record, course, record_status="READY")
        for code, (record, course) in sorted(current_by_code.items())
    ]
    return {
        "required": all_codes,
        "satisfied": satisfied,
        "missing": missing_unique if satisfied_group is None else [],
        "expired": expired,
        "records": records,
        "passed": satisfied_group is not None,
        "alternative_groups": groups,
        "satisfied_group": satisfied_group,
    }


def _payload_from_training_status_item(
    code: str,
    course: Any,
    item: Any,
    *,
    as_of: date,
    record: Any | None = None,
) -> dict[str, Any]:
    """Build a People competence row from Training's policy status item."""

    completion = getattr(item, "last_completion_date", None)
    valid_until = getattr(item, "valid_until", None)
    days = getattr(item, "days_until_due", None)
    status = enum_text(getattr(item, "status", None)) or "NOT_DONE"
    if record is not None:
        payload = _tracked_record_payload(code, record, course, as_of=as_of)
    else:
        payload = {
            "record_id": None,
            "course_id": str(getattr(course, "id", "") or "") or None,
            "course_code": code,
            "course_name": getattr(course, "course_name", None),
            "source_course_code": str(getattr(course, "course_id", "") or "").strip().upper() or None,
            "completion_date": completion.isoformat() if completion else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
            "verification_status": "VERIFIED" if completion else "NONE",
            "record_status": "READY" if status in {"OK", "DUE_SOON", "DEFERRED"} else ("EXPIRED" if status == "OVERDUE" else "MISSING"),
            "source_route": None,
            "days_until_expiry": days if isinstance(days, int) else _days_until(valid_until, as_of=as_of),
        }
    payload["training_status"] = status
    payload["days_until_expiry"] = days if isinstance(days, int) else payload.get("days_until_expiry")
    if completion and not payload.get("completion_date"):
        payload["completion_date"] = completion.isoformat()
    if valid_until and not payload.get("valid_until"):
        payload["valid_until"] = valid_until.isoformat()
    return payload


def _tracked_from_training_policy(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    as_of: date,
    codes: list[str],
) -> dict[str, dict[str, Any]]:
    """Reuse Training ``evaluate_user_training_policy`` for QMS competence pills.

    Same engine Training uses for Quality-department never-completed / overdue
    detection (requirements + role rules + verified records).
    """

    wanted = _normalize_codes(codes)
    if not wanted:
        return {}

    try:
        from amodb.apps.accounts import models as account_models
        from . import compliance
    except Exception:
        return {}

    user = (
        db.query(account_models.User)
        .options(noload("*"))
        .filter(account_models.User.amo_id == amo_id, account_models.User.id == user_id)
        .first()
    )
    if user is None or not hasattr(user, "id"):
        return {}

    try:
        # One policy pass is enough: full catalogue includes mandatory items and
        # still surfaces QMS-family history for People pills.
        full_eval = compliance.evaluate_user_training_policy(db, user, required_only=False, today=as_of)
    except Exception:
        return {}

    items_by_short: dict[str, Any] = {}
    for item in getattr(full_eval, "items", []) or []:
        items_by_short[str(getattr(item, "course_id", "") or "").strip().upper()] = item
    for item in getattr(full_eval, "mandatory_items", None) or []:
        items_by_short[str(getattr(item, "course_id", "") or "").strip().upper()] = item

    try:
        qms_family_courses = (
            db.query(models.TrainingCourse)
            .options(noload("*"))
            .filter(
                models.TrainingCourse.amo_id == amo_id,
                models.TrainingCourse.is_active.is_(True),
                or_(
                    func.upper(models.TrainingCourse.course_id).in_(list(wanted)),
                    func.upper(models.TrainingCourse.group_code) == _QMS_GROUP_CODE,
                    models.TrainingCourse.category == models.TrainingCourseCategory.QUALITY_SYSTEMS,
                ),
            )
            .all()
        )
    except Exception:
        qms_family_courses = []

    # Also accept punctuation variants of canonical codes already in the policy map.
    short_codes = set(items_by_short)
    for course in qms_family_courses:
        short = str(getattr(course, "course_id", "") or "").strip().upper()
        if short:
            short_codes.add(short)

    if not short_codes:
        return {}

    try:
        courses = (
            db.query(models.TrainingCourse)
            .options(noload("*"))
            .filter(
                models.TrainingCourse.amo_id == amo_id,
                func.upper(models.TrainingCourse.course_id).in_(sorted(short_codes)),
            )
            .all()
        )
    except Exception:
        courses = list(qms_family_courses)

    courses = [course for course in courses if getattr(course, "course_id", None)]
    # Ensure structured QMS family rows are present even if course_id casing differed.
    seen_ids = {str(getattr(course, "id", "")) for course in courses}
    for course in qms_family_courses:
        if str(getattr(course, "id", "")) not in seen_ids:
            courses.append(course)
            seen_ids.add(str(getattr(course, "id", "")))

    course_by_short = {str(course.course_id or "").strip().upper(): course for course in courses}
    course_pks = [str(course.id) for course in courses if getattr(course, "id", None)]
    try:
        latest_records = compliance._latest_records_for_user(db, user, course_pks) if course_pks else {}
    except Exception:
        latest_records = {}

    # Synthesize status items for QMS family courses missing from the policy map
    # (should be rare; full_eval normally covers the active catalogue).
    for course in courses:
        short = str(course.course_id or "").strip().upper()
        if short in items_by_short:
            continue
        if not canonicalize_qms_competence_code(course, requested=wanted):
            continue
        record = latest_records.get(str(course.id))
        items_by_short[short] = compliance.build_status_item_from_dates(
            course=course,
            last_completion_date=getattr(record, "completion_date", None) if record else None,
            due_date=getattr(record, "valid_until", None) if record else None,
            deferral_due=None,
            upcoming_event_id=None,
            upcoming_event_date=None,
            today=as_of,
        )

    tracked: dict[str, dict[str, Any]] = {}
    for short, item in items_by_short.items():
        course = course_by_short.get(short)
        if course is None:
            continue
        canonical = canonicalize_qms_competence_code(course, requested=wanted)
        if not canonical:
            continue
        record = latest_records.get(str(course.id))
        payload = _payload_from_training_status_item(
            canonical,
            course,
            item,
            as_of=as_of,
            record=record,
        )
        existing = tracked.get(canonical)
        if existing is None:
            tracked[canonical] = payload
            continue
        if payload.get("completion_date") and not existing.get("completion_date"):
            tracked[canonical] = payload
        elif payload.get("completion_date") and existing.get("completion_date"):
            if (payload.get("valid_until") or "") >= (existing.get("valid_until") or ""):
                tracked[canonical] = payload
    return tracked


def _policy_row_is_current(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    status = enum_text(row.get("training_status"))
    return status in _POLICY_CURRENT_STATUSES


def _policy_row_is_overdue(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    if enum_text(row.get("training_status")) == "OVERDUE":
        return True
    days = row.get("days_until_expiry")
    return isinstance(days, int) and days < 0 and bool(row.get("completion_date"))


def qms_auditor_competence_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    as_of: date,
    track_admin: bool = True,
) -> dict[str, Any]:
    """Evaluate QMS auditor currency from Training's policy evaluation only.

    Currency is (QMS-INIT OR current QMS-REF). QMS-ADMIN is tracked for
    auto-suspend when held and expired, never as a hard eligibility requirement.

    Display and gates both read ``evaluate_user_training_policy`` — the same
    requirement / role-rule / record path Training people-compliance uses.
    """

    codes = list(QMS_COMPETENCE_CODES)
    policy_tracked = _tracked_from_training_policy(
        db,
        amo_id=amo_id,
        user_id=user_id,
        as_of=as_of,
        codes=codes,
    )

    satisfied: list[str] = []
    missing: list[str] = []
    expired: list[str] = []
    expired_records: list[dict[str, Any]] = []
    tracked_records: list[dict[str, Any]] = []
    current_records: list[dict[str, Any]] = []

    for code in QMS_CURRENCY_CODES:
        row = policy_tracked.get(code)
        # Surface rows Training already knows about when there is displayable history
        # (completion / expiry / current / overdue). Pure NOT_DONE stays in missing only
        # so People pills render "missing" rather than a blank chip payload.
        if row and (
            row.get("completion_date")
            or row.get("valid_until")
            or _policy_row_is_current(row)
            or _policy_row_is_overdue(row)
        ):
            tracked_records.append(row)
        if _policy_row_is_current(row):
            satisfied.append(code)
            if row:
                current_records.append(row)
            continue
        if _policy_row_is_overdue(row):
            expired.append(code)
            missing.append(code)
            if row:
                expired_records.append(row)
            continue
        missing.append(code)

    satisfied_group: list[str] | None = None
    if QMS_REF in satisfied:
        satisfied_group = [QMS_REF]
    elif QMS_INIT in satisfied:
        satisfied_group = [QMS_INIT]
    passed = satisfied_group is not None

    admin_row = policy_tracked.get(QMS_ADMIN)
    if admin_row:
        tracked_records.append(admin_row)
    if _policy_row_is_current(admin_row):
        admin_payload: dict[str, Any] = {
            "status": "current",
            "course_code": QMS_ADMIN,
            "record": admin_row,
        }
    elif _policy_row_is_overdue(admin_row):
        admin_payload = {
            "status": "expired",
            "course_code": QMS_ADMIN,
            "record": admin_row,
        }
        expired_records.append(admin_row)
    elif admin_row and admin_row.get("completion_date"):
        admin_payload = {
            "status": "pending_or_inactive",
            "course_code": QMS_ADMIN,
            "record": admin_row,
        }
    else:
        admin_payload = {"status": "none", "course_code": QMS_ADMIN, "record": admin_row}

    admin_lapsed = track_admin and admin_payload["status"] == "expired"
    currency_lapsed = (not passed) and bool(expired)
    # When currency OR is satisfied, the unheld alternate is not a hard miss.
    # Keep it out of ``missing`` so People pills / trainingMissing gates stay accurate.
    hard_missing = [] if passed else list(missing)
    return {
        "required": list(QMS_CURRENCY_CODES),
        "satisfied": satisfied,
        "missing": hard_missing,
        "expired": expired,
        "records": current_records or tracked_records,
        "passed": passed,
        "alternative_groups": [[QMS_INIT], [QMS_REF]],
        "satisfied_group": satisfied_group,
        "currency_passed": passed,
        "currency_lapsed": currency_lapsed,
        "admin": admin_payload,
        "admin_lapsed": admin_lapsed,
        "expired_records": expired_records,
        "tracked_records": tracked_records,
        "track_admin": track_admin,
        "suspend_recommended": currency_lapsed or admin_lapsed,
        "source": "training_policy",
        "package": {
            "currency_any_of": list(QMS_CURRENCY_CODES),
            "tracked_admin": QMS_ADMIN if track_admin else None,
        },
    }


@dataclass(frozen=True)
class TrainingRecordSummary:
    total_current: int = 0
    expired: int = 0
    expiring: int = 0
    unverified: int = 0
    oldest_expiry: date | None = None


def training_record_summary(
    db: Session,
    *,
    amo_id: str,
    as_of: date,
    due_days: int = 30,
) -> TrainingRecordSummary:
    """Aggregate latest evidence once per tenant/user/course.

    Historical renewals do not inflate QMS exposure, and unverified rows never
    improve the compliance result.
    """

    ranked = (
        db.query(
            models.TrainingRecord.id.label("record_id"),
            models.TrainingRecord.valid_until.label("valid_until"),
            models.TrainingRecord.verification_status.label("verification_status"),
            func.row_number().over(
                partition_by=(models.TrainingRecord.user_id, models.TrainingRecord.course_id),
                order_by=(
                    models.TrainingRecord.valid_until.desc().nullslast(),
                    models.TrainingRecord.completion_date.desc().nullslast(),
                    models.TrainingRecord.created_at.desc().nullslast(),
                    models.TrainingRecord.id.desc(),
                ),
            ).label("record_rank"),
        )
        .filter(
            models.TrainingRecord.amo_id == amo_id,
            record_lifecycle.active_records_filter(models.TrainingRecord),
        )
        .subquery()
    )
    latest = db.query(
        ranked.c.valid_until,
        ranked.c.verification_status,
    ).filter(ranked.c.record_rank == 1).subquery()
    verified = latest.c.verification_status == models.TrainingRecordVerificationStatus.VERIFIED
    pending = latest.c.verification_status == models.TrainingRecordVerificationStatus.PENDING
    due_on = as_of + timedelta(days=max(0, due_days))

    total_current, expired, expiring, unverified, oldest_expiry = db.query(
        func.count().label("total_current"),
        func.sum(case((and_(verified, latest.c.valid_until.is_not(None), latest.c.valid_until < as_of), 1), else_=0)).label("expired"),
        func.sum(case((and_(verified, latest.c.valid_until >= as_of, latest.c.valid_until <= due_on), 1), else_=0)).label("expiring"),
        func.sum(case((pending, 1), else_=0)).label("unverified"),
        func.min(case((and_(verified, latest.c.valid_until < as_of), latest.c.valid_until), else_=None)).label("oldest_expiry"),
    ).one()
    return TrainingRecordSummary(
        total_current=int(total_current or 0),
        expired=int(expired or 0),
        expiring=int(expiring or 0),
        unverified=int(unverified or 0),
        oldest_expiry=oldest_expiry,
    )
