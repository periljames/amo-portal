from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import catalog, common, models, schemas
from .code_registry_models import (
    RosterCalendarMode,
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)


@dataclass(frozen=True)
class StarterShift:
    code: str
    label: str
    kind: models.ShiftTemplateKind
    start: Optional[str]
    end: Optional[str]
    duration_minutes: Optional[int]
    counts_as_duty: bool
    unpaid_break_minutes: int
    calendar_mode: RosterCalendarMode
    duty_semantic: RosterDutySemantic
    description: str


# Keep the starter registry intentionally small. Tenants define their own shift
# windows and additional codes (SA, XH, nights, split duties, etc.) and choose
# whether each template counts as duty. Nothing here assigns operational times.
AMO_STARTER_SHIFTS: tuple[StarterShift, ...] = (
    StarterShift(
        "D",
        "Day Duty",
        models.ShiftTemplateKind.DAY,
        None,
        None,
        None,
        True,
        0,
        RosterCalendarMode.TIMED,
        RosterDutySemantic.DUTY,
        "Normal day duty. Configure the local start/end window for the tenant or work pattern.",
    ),
    StarterShift(
        "X",
        "On-site Standby / Duty",
        models.ShiftTemplateKind.STANDBY,
        None,
        None,
        None,
        True,
        0,
        RosterCalendarMode.TIMED,
        RosterDutySemantic.STANDBY,
        "On-site standby or duty. Configure the local window; it always participates in duty/rest calculations while counts_as_duty is enabled.",
    ),
    StarterShift(
        "RD",
        "Rest Day",
        models.ShiftTemplateKind.OFF,
        None,
        None,
        0,
        False,
        0,
        RosterCalendarMode.ALL_DAY,
        RosterDutySemantic.REST,
        "Explicit protected rest day. OFF and rest-day concepts are represented by this single canonical code.",
    ),
)

STARTER_CODES = tuple(item.code for item in AMO_STARTER_SHIFTS)
SHIFT_CODE_PATTERN = re.compile(r"^[A-Z0-9]{1,2}$")
CANONICAL_CODE_EQUIVALENTS = {
    "O": "RD",
    "OF": "RD",
    "RR": "RD",
}


def normalize_shift_code(value: str) -> str:
    code = str(value or "").strip().upper()
    if not SHIFT_CODE_PATTERN.fullmatch(code):
        raise ValueError(
            "Shift code must be one or two uppercase letters/numbers (for example D, X or RD)."
        )
    return CANONICAL_CODE_EQUIVALENTS.get(code, code)


def _ensure_unique_code(
    db: Session,
    *,
    amo_id: str,
    code: str,
    exclude_template_id: Optional[str] = None,
) -> None:
    query = db.query(models.ShiftTemplate.id).filter(
        models.ShiftTemplate.amo_id == amo_id,
        func.upper(models.ShiftTemplate.code) == code,
    )
    if exclude_template_id:
        query = query.filter(models.ShiftTemplate.id != exclude_template_id)
    if query.first():
        raise ValueError(f"Roster code {code} already exists for this tenant")


def create_shift_template(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.ShiftTemplateCreate,
) -> models.ShiftTemplate:
    code = normalize_shift_code(payload.code)
    _ensure_unique_code(db, amo_id=amo_id, code=code)
    normalized = payload.model_copy(update={"code": code})
    return catalog.create_shift_template(
        db, amo_id=amo_id, actor_user_id=actor_user_id, payload=normalized
    )


def update_shift_template(
    db: Session,
    *,
    row: models.ShiftTemplate,
    actor_user_id: str,
    payload: schemas.ShiftTemplateUpdate,
) -> models.ShiftTemplate:
    normalized = payload
    if "code" in payload.model_fields_set and payload.code is not None:
        code = normalize_shift_code(payload.code)
        _ensure_unique_code(
            db, amo_id=row.amo_id, code=code, exclude_template_id=row.id
        )
        normalized = payload.model_copy(update={"code": code})
    return catalog.update_shift_template(
        db, row=row, actor_user_id=actor_user_id, payload=normalized
    )


def _implicit_seed_disabled(
    db: Session, *, amo_id: str, actor_user_id: Optional[str] = None
) -> None:
    return None


def install_catalog_policy() -> None:
    catalog.seed_default_shift_templates = _implicit_seed_disabled


def install_service_policy(service_module) -> None:
    service_module.create_shift_template = create_shift_template
    service_module.update_shift_template = update_shift_template


def install_starter_pack(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> tuple[list[models.ShiftTemplate], list[str]]:
    """Install canonical configurable D, X and RD templates.

    Setup is deliberately destructive for equivalent historical rest codes:
    O/OF/RR references are moved to RD and the duplicate templates are deleted
    before the minimal starter registry is reconciled. Unrelated working codes
    are left tenant-owned rather than guessed into another meaning.
    """

    # Local import avoids a module cycle while making the normal setup action
    # perform the requested destructive rest-code consolidation automatically.
    from .rest_code_canonicalization import canonicalize_rest_codes

    try:
        canonicalize_rest_codes(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
        )
    except LookupError:
        # A new tenant may not have any historical rest template yet; RD will
        # be created below as part of the canonical starter set.
        pass

    existing = {
        row.code.upper(): row
        for row in db.query(models.ShiftTemplate)
        .filter(models.ShiftTemplate.amo_id == amo_id)
        .all()
    }
    created: list[models.ShiftTemplate] = []
    skipped: list[str] = []
    for order, item in enumerate(AMO_STARTER_SHIFTS, start=1):
        if item.code in existing:
            skipped.append(item.code)
            continue
        payload = schemas.ShiftTemplateCreate(
            code=item.code,
            label=item.label,
            kind=item.kind,
            default_start_time=item.start,
            default_end_time=item.end,
            duration_minutes=item.duration_minutes,
            counts_as_duty=item.counts_as_duty,
            is_active=True,
            display_order=order * 10,
            description=item.description,
            color_token=f"shift-{item.code.lower()}",
            icon_name=None,
        )
        template = catalog.create_shift_template(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        policy = RosterShiftTemplatePolicy(
            amo_id=amo_id,
            shift_template_id=template.id,
            unpaid_break_minutes=item.unpaid_break_minutes,
            calendar_mode=item.calendar_mode,
            duty_semantic=item.duty_semantic,
            verification_status=RosterCodeVerificationStatus.CONFIRMED,
            source_reference="AMO Portal minimal starter pack; tenant-owned after installation.",
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(policy)
        created.append(template)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterShiftStarterPack",
        entity_id=amo_id,
        action="install",
        after={"created_codes": [row.code for row in created], "skipped_codes": skipped},
    )
    return created, skipped


def template_usage_count(db: Session, *, amo_id: str, template_id: str) -> int:
    return int(
        db.query(func.count(models.RosterAssignment.id))
        .filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterAssignment.shift_template_id == template_id,
        )
        .scalar()
        or 0
    )


def delete_unused_template(
    db: Session,
    *,
    amo_id: str,
    template_id: str,
    actor_user_id: str,
) -> None:
    row = (
        db.query(models.ShiftTemplate)
        .filter(models.ShiftTemplate.amo_id == amo_id, models.ShiftTemplate.id == template_id)
        .first()
    )
    if not row:
        raise LookupError("Shift template not found")
    usage = template_usage_count(db, amo_id=amo_id, template_id=template_id)
    if usage:
        raise ValueError(
            "This code is still referenced by roster records. Reassign those records to the canonical replacement before deleting the template."
        )
    before = {"code": row.code, "label": row.label, "is_active": row.is_active}
    db.delete(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="ShiftTemplate",
        entity_id=template_id,
        action="delete_unused",
        before=before,
        critical=True,
    )


def policy_for_template(
    db: Session,
    *,
    amo_id: str,
    template_id: str,
) -> Optional[RosterShiftTemplatePolicy]:
    return (
        db.query(RosterShiftTemplatePolicy)
        .filter(
            RosterShiftTemplatePolicy.amo_id == amo_id,
            RosterShiftTemplatePolicy.shift_template_id == template_id,
        )
        .first()
    )
