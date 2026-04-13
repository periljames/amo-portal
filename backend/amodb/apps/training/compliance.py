from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, load_only, noload

from ..accounts import models as accounts_models
from . import models as training_models
from . import schemas as training_schemas


REMINDER_DAY_MARKS: tuple[int, ...] = (60, 30, 15, -1)
PORTAL_LOCKOUT_DAYS_OVERDUE = 1


@dataclass(frozen=True)
class TrainingPolicyEvaluation:
    items: List[training_schemas.TrainingStatusItem]
    mandatory_items: List[training_schemas.TrainingStatusItem]
    overdue_items: List[training_schemas.TrainingStatusItem]
    due_soon_items: List[training_schemas.TrainingStatusItem]
    deferred_items: List[training_schemas.TrainingStatusItem]
    scheduled_items: List[training_schemas.TrainingStatusItem]
    not_done_items: List[training_schemas.TrainingStatusItem]
    ok_items: List[training_schemas.TrainingStatusItem]
    portal_locked: bool
    portal_lock_reasons: List[str]
    crs_blocked: bool
    crs_block_reasons: List[str]


def is_training_editor(user: accounts_models.User) -> bool:
    if getattr(user, "is_system_account", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False):
        return True
    if user.role == accounts_models.AccountRole.QUALITY_MANAGER:
        return True
    dept = getattr(user, "department", None)
    code = getattr(dept, "code", "") if dept is not None else ""
    return isinstance(code, str) and code.upper() == "QUALITY"


def get_user_department_code(user: accounts_models.User) -> Optional[str]:
    dept = getattr(user, "department", None)
    code = getattr(dept, "code", None) if dept is not None else None
    return code.upper() if isinstance(code, str) and code.strip() else None


def get_user_job_role(user: accounts_models.User) -> Optional[str]:
    for attr in ("job_role", "job_title", "position", "title", "designation", "position_title"):
        value = getattr(user, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def add_months(base: date, months: int) -> date:
    if months <= 0:
        return base
    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    days_in_month = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][month - 1]
    day = min(base.day, days_in_month)
    return date(year, month, day)


def _normalized_course_text(course: training_models.TrainingCourse) -> str:
    values: list[str] = []
    for attr in (
        "course_id",
        "course_name",
        "category_raw",
        "scope",
        "regulatory_reference",
    ):
        value = getattr(course, attr, None)
        if isinstance(value, str) and value.strip():
            values.append(value.strip().lower())
    return " ".join(values)


def is_initial_course(course: training_models.TrainingCourse) -> bool:
    """Best-effort classifier for initial / first-time courses.

    Legacy datasets mix enum kind, raw import status, and naming conventions.
    The importer relies on this helper when deciding whether a course is one-off
    or part of a recurrent chain, so it should accept the common legacy labels
    without requiring perfect normalization.
    """
    kind = getattr(course, "kind", None)
    if kind == training_models.TrainingKind.INITIAL:
        return True

    status = getattr(course, "status", None)
    if isinstance(status, str) and status.strip().upper() == "INITIAL":
        return True

    text = _normalized_course_text(course)
    if not text:
        return False

    padded = f" {text.replace('-', ' ').replace('_', ' ')} "
    initial_markers = (
        " initial ",
        " init ",
        " induction ",
        " ab initio ",
        " new hire ",
        " onboarding ",
        " familiarization ",
        " familiarisation ",
    )
    return any(marker in padded for marker in initial_markers)




def _extract_status_from_remarks(remarks: Optional[str]) -> Optional[str]:
    if not remarks:
        return None
    match = re.search(r"(?:^|\|)\s*(?:LifecycleStatus|Status)\s*=\s*([^|]+?)\s*(?:\||$)", remarks, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() or None

def _normalize_training_state_label(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().upper()
    if not raw:
        return None
    aliases = {
        "COMPLIANT": "OK",
        "CURRENT": "OK",
        "IN_DATE": "OK",
        "IN-DATE": "OK",
    }
    return aliases.get(raw, raw)


def build_status_item_from_dates(
    *,
    course: training_models.TrainingCourse,
    last_completion_date: Optional[date],
    due_date: Optional[date],
    deferral_due: Optional[date],
    upcoming_event_id: Optional[str],
    upcoming_event_date: Optional[date],
    today: date,
    source_record_status: Optional[str] = None,
    source_status: Optional[str] = None,
) -> training_schemas.TrainingStatusItem:
    controlling_due = due_date
    if deferral_due and (controlling_due is None or deferral_due > controlling_due):
        controlling_due = deferral_due

    status_label = "NOT_DONE"
    days_until_due: Optional[int] = None
    if controlling_due:
        days_until_due = (controlling_due - today).days
        if days_until_due < 0:
            status_label = "OVERDUE"
        elif days_until_due <= 60:
            status_label = "DUE_SOON"
        else:
            status_label = "OK"

    if deferral_due and controlling_due and days_until_due is not None and days_until_due >= 0:
        status_label = "DEFERRED"

    explicit_status = _normalize_training_state_label(source_record_status) or _normalize_training_state_label(source_status)
    if explicit_status == "OK" and last_completion_date is not None and status_label not in {"DEFERRED", "SCHEDULED_ONLY"}:
        status_label = "OK"
    elif explicit_status in {"OVERDUE", "DUE_SOON", "NOT_DONE", "SCHEDULED_ONLY", "DEFERRED"}:
        status_label = explicit_status

    if last_completion_date is None and upcoming_event_date and status_label == "NOT_DONE":
        status_label = "SCHEDULED_ONLY"

    return training_schemas.TrainingStatusItem(
        course_id=course.course_id,
        course_name=course.course_name,
        frequency_months=course.frequency_months,
        last_completion_date=last_completion_date,
        valid_until=due_date,
        extended_due_date=controlling_due,
        days_until_due=days_until_due,
        status=status_label,
        upcoming_event_id=upcoming_event_id,
        upcoming_event_date=upcoming_event_date,
    )


def get_required_course_ids_for_user(db: Session, user: accounts_models.User) -> List[str]:
    reqs = (
        db.query(training_models.TrainingRequirement)
        .options(
            noload("*"),
            load_only(
                training_models.TrainingRequirement.id,
                training_models.TrainingRequirement.course_id,
                training_models.TrainingRequirement.scope,
                training_models.TrainingRequirement.department_code,
                training_models.TrainingRequirement.job_role,
                training_models.TrainingRequirement.user_id,
                training_models.TrainingRequirement.is_active,
            ),
        )
        .filter(
            training_models.TrainingRequirement.amo_id == user.amo_id,
            training_models.TrainingRequirement.is_active.is_(True),
        )
        .all()
    )

    dept_code = get_user_department_code(user)
    job_role = get_user_job_role(user)
    required_course_ids: List[str] = []

    if reqs:
        for req in reqs:
            if req.scope == training_models.TrainingRequirementScope.ALL:
                required_course_ids.append(req.course_id)
            elif req.scope == training_models.TrainingRequirementScope.USER and req.user_id == user.id:
                required_course_ids.append(req.course_id)
            elif req.scope == training_models.TrainingRequirementScope.DEPARTMENT and dept_code and req.department_code and req.department_code.upper() == dept_code:
                required_course_ids.append(req.course_id)
            elif req.scope == training_models.TrainingRequirementScope.JOB_ROLE and job_role and req.job_role and req.job_role.strip().lower() == job_role.lower():
                required_course_ids.append(req.course_id)
    else:
        required_course_ids = [
            c.id
            for c in db.query(training_models.TrainingCourse)
            .options(noload("*"), load_only(training_models.TrainingCourse.id))
            .filter(
                training_models.TrainingCourse.amo_id == user.amo_id,
                training_models.TrainingCourse.is_active.is_(True),
                training_models.TrainingCourse.is_mandatory.is_(True),
            )
            .all()
        ]

    return sorted(set(required_course_ids))


def get_courses_for_user(db: Session, user: accounts_models.User, *, required_only: bool = False) -> List[training_models.TrainingCourse]:
    q = db.query(training_models.TrainingCourse).options(
        noload("*"),
        load_only(
            training_models.TrainingCourse.id,
            training_models.TrainingCourse.course_id,
            training_models.TrainingCourse.course_name,
            training_models.TrainingCourse.frequency_months,
            training_models.TrainingCourse.is_mandatory,
            training_models.TrainingCourse.is_active,
            training_models.TrainingCourse.status,
            training_models.TrainingCourse.category_raw,
            training_models.TrainingCourse.scope,
        ),
    ).filter(
        training_models.TrainingCourse.amo_id == user.amo_id,
        training_models.TrainingCourse.is_active.is_(True),
    )
    if required_only:
        course_ids = get_required_course_ids_for_user(db, user)
        if not course_ids:
            return []
        q = q.filter(training_models.TrainingCourse.id.in_(course_ids))
    return q.order_by(training_models.TrainingCourse.course_id.asc()).all()


def _latest_records_for_user(db: Session, user: accounts_models.User, course_ids: Sequence[str]) -> Dict[str, training_models.TrainingRecord]:
    if not course_ids:
        return {}
    rows = (
        db.query(training_models.TrainingRecord)
        .options(
            noload("*"),
            load_only(
                training_models.TrainingRecord.course_id,
                training_models.TrainingRecord.completion_date,
                training_models.TrainingRecord.valid_until,
                training_models.TrainingRecord.remarks,
            ),
        )
        .filter(
            training_models.TrainingRecord.amo_id == user.amo_id,
            training_models.TrainingRecord.user_id == user.id,
            training_models.TrainingRecord.course_id.in_(course_ids),
        )
        .order_by(training_models.TrainingRecord.course_id.asc(), training_models.TrainingRecord.completion_date.desc())
        .all()
    )
    latest: Dict[str, training_models.TrainingRecord] = {}
    for row in rows:
        latest.setdefault(row.course_id, row)
    return latest


def _latest_deferrals_for_user(db: Session, user: accounts_models.User, course_ids: Sequence[str]) -> Dict[str, training_models.TrainingDeferralRequest]:
    if not course_ids:
        return {}
    rows = (
        db.query(training_models.TrainingDeferralRequest)
        .options(
            noload("*"),
            load_only(
                training_models.TrainingDeferralRequest.course_id,
                training_models.TrainingDeferralRequest.requested_new_due_date,
            ),
        )
        .filter(
            training_models.TrainingDeferralRequest.amo_id == user.amo_id,
            training_models.TrainingDeferralRequest.user_id == user.id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status == training_models.DeferralStatus.APPROVED,
        )
        .order_by(training_models.TrainingDeferralRequest.course_id.asc(), training_models.TrainingDeferralRequest.requested_new_due_date.desc())
        .all()
    )
    latest: Dict[str, training_models.TrainingDeferralRequest] = {}
    for row in rows:
        latest.setdefault(row.course_id, row)
    return latest


def _earliest_events_for_user(db: Session, user: accounts_models.User, course_ids: Sequence[str], today: date) -> Dict[str, Tuple[str, date]]:
    if not course_ids:
        return {}
    rows = (
        db.query(
            training_models.TrainingEvent.id,
            training_models.TrainingEvent.course_id,
            training_models.TrainingEvent.starts_on,
        )
        .join(training_models.TrainingEventParticipant, training_models.TrainingEvent.id == training_models.TrainingEventParticipant.event_id)
        .filter(
            training_models.TrainingEvent.amo_id == user.amo_id,
            training_models.TrainingEvent.course_id.in_(course_ids),
            training_models.TrainingEvent.starts_on >= today,
            training_models.TrainingEvent.status == training_models.TrainingEventStatus.PLANNED,
            training_models.TrainingEventParticipant.user_id == user.id,
            training_models.TrainingEventParticipant.status.in_(
                [
                    training_models.TrainingParticipantStatus.SCHEDULED,
                    training_models.TrainingParticipantStatus.INVITED,
                    training_models.TrainingParticipantStatus.CONFIRMED,
                ]
            ),
        )
        .order_by(training_models.TrainingEvent.course_id.asc(), training_models.TrainingEvent.starts_on.asc())
        .all()
    )
    earliest: Dict[str, Tuple[str, date]] = {}
    for event_id, course_id, starts_on in rows:
        earliest.setdefault(course_id, (event_id, starts_on))
    return earliest


def evaluate_user_training_policy(
    db: Session,
    user: accounts_models.User,
    *,
    required_only: bool = False,
    today: Optional[date] = None,
) -> TrainingPolicyEvaluation:
    today = today or date.today()
    courses = get_courses_for_user(db, user, required_only=required_only)
    if not courses:
        empty: List[training_schemas.TrainingStatusItem] = []
        return TrainingPolicyEvaluation(empty, empty, empty, empty, empty, empty, empty, empty, False, [], False, [])

    course_ids = [course.id for course in courses]
    latest_record = _latest_records_for_user(db, user, course_ids)
    latest_deferral = _latest_deferrals_for_user(db, user, course_ids)
    earliest_event = _earliest_events_for_user(db, user, course_ids, today)

    items: List[training_schemas.TrainingStatusItem] = []
    for course in courses:
        record = latest_record.get(course.id)
        deferral = latest_deferral.get(course.id)
        event_info = earliest_event.get(course.id)
        due_date = None
        if record:
            due_date = record.valid_until or (add_months(record.completion_date, course.frequency_months) if course.frequency_months else None)
        upcoming_event_id = event_info[0] if event_info else None
        upcoming_event_date = event_info[1] if event_info else None
        items.append(
            build_status_item_from_dates(
                course=course,
                last_completion_date=record.completion_date if record else None,
                due_date=due_date,
                deferral_due=deferral.requested_new_due_date if deferral else None,
                upcoming_event_id=upcoming_event_id,
                upcoming_event_date=upcoming_event_date,
                today=today,
                source_record_status=_extract_status_from_remarks(getattr(record, "remarks", None)) if record else None,
                source_status=None,
            )
        )

    mandatory_course_codes = {c.course_id for c in courses if c.is_mandatory}
    mandatory_items = [item for item in items if item.course_id in mandatory_course_codes]
    overdue_items = [item for item in mandatory_items if item.status == "OVERDUE"]
    due_soon_items = [item for item in mandatory_items if item.status == "DUE_SOON"]
    deferred_items = [item for item in mandatory_items if item.status == "DEFERRED"]
    scheduled_items = [item for item in mandatory_items if item.status == "SCHEDULED_ONLY"]
    not_done_items = [item for item in mandatory_items if item.status == "NOT_DONE"]
    ok_items = [item for item in mandatory_items if item.status == "OK"]

    portal_lock_reasons = [
        f"{item.course_name} is overdue by {abs(item.days_until_due or 0)} day(s)."
        for item in overdue_items
        if (item.days_until_due or 0) <= -PORTAL_LOCKOUT_DAYS_OVERDUE
    ]
    portal_locked = bool(portal_lock_reasons) and not is_training_editor(user)

    crs_block_reasons = [
        f"{item.course_name} is overdue by {abs(item.days_until_due or 0)} day(s)."
        for item in overdue_items
    ]
    crs_blocked = bool(crs_block_reasons)

    return TrainingPolicyEvaluation(
        items=items,
        mandatory_items=mandatory_items,
        overdue_items=overdue_items,
        due_soon_items=due_soon_items,
        deferred_items=deferred_items,
        scheduled_items=scheduled_items,
        not_done_items=not_done_items,
        ok_items=ok_items,
        portal_locked=portal_locked,
        portal_lock_reasons=portal_lock_reasons,
        crs_blocked=crs_blocked,
        crs_block_reasons=crs_block_reasons,
    )


def build_user_access_state(db: Session, user: accounts_models.User, *, today: Optional[date] = None) -> training_schemas.TrainingAccessState:
    evaluation = evaluate_user_training_policy(db, user, required_only=True, today=today)
    primary_reason = evaluation.portal_lock_reasons[0] if evaluation.portal_lock_reasons else None
    return training_schemas.TrainingAccessState(
        user_id=str(user.id),
        portal_locked=evaluation.portal_locked,
        portal_lock_reason=primary_reason,
        crs_blocked=evaluation.crs_blocked,
        overdue_mandatory_count=len(evaluation.overdue_items),
        due_soon_mandatory_count=len(evaluation.due_soon_items),
        deferred_mandatory_count=len(evaluation.deferred_items),
        not_done_mandatory_count=len(evaluation.not_done_items),
        ok_mandatory_count=len(evaluation.ok_items),
        upcoming_scheduled_count=len(evaluation.scheduled_items),
    )
