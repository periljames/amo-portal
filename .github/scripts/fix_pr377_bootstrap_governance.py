from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch anchor missing in {path}: {old[:160]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "backend/amodb/apps/workforce/hr_service.py",
    "from datetime import date, datetime, timedelta, timezone\nfrom typing import Optional\n",
    "from datetime import date, datetime, timedelta, timezone\nfrom typing import Optional\nfrom uuid import NAMESPACE_URL, uuid4, uuid5\n",
)
replace_once(
    "backend/amodb/apps/workforce/hr_service.py",
    "from ..accounts import models as account_models\nfrom . import hr_schemas, models, permissions, schemas, services\n",
    "from ..accounts import models as account_models\nfrom ..audit import schemas as audit_schemas\nfrom ..audit import services as audit_services\nfrom . import hr_schemas, models, permissions, schemas, services\n",
)

service_path = ROOT / "backend/amodb/apps/workforce/hr_service.py"
service_text = service_path.read_text(encoding="utf-8")
start = service_text.index("def bootstrap_default_day_pattern(\n")
old_function = service_text[start:]
new_block = r'''_DEFAULT_DAY_SHIFT_CODE = "DEFAULT-DAY"
_DEFAULT_DAY_PATTERN_CODE = "DEFAULT-DAY-5X2"
_DEFAULT_DAY_SHIFT_KEY = "workforce.default-day.shift.v1"
_DEFAULT_DAY_PATTERN_KEY = "workforce.default-day.pattern.v1"


def _default_day_system_id(*, amo_id: str, system_key: str) -> str:
    """Return the immutable tenant-scoped identity for a portal-owned baseline."""
    return str(uuid5(NAMESPACE_URL, f"amo-portal:{amo_id}:{system_key}"))


def _shift_template_snapshot(row) -> dict:
    return {
        "code": row.code,
        "label": row.label,
        "kind": _value(row.kind),
        "default_start_time": row.default_start_time,
        "default_end_time": row.default_end_time,
        "duration_minutes": row.duration_minutes,
        "counts_as_duty": bool(row.counts_as_duty),
        "is_active": bool(row.is_active),
        "display_order": row.display_order,
        "description": row.description,
        "icon_name": row.icon_name,
    }


def _work_pattern_snapshot(db: Session, row: models.WorkPattern) -> dict:
    days = db.query(models.WorkPatternDay).filter(
        models.WorkPatternDay.amo_id == row.amo_id,
        models.WorkPatternDay.work_pattern_id == row.id,
    ).order_by(models.WorkPatternDay.cycle_day_index.asc(), models.WorkPatternDay.id.asc()).all()
    return {
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "cycle_length_days": row.cycle_length_days,
        "is_active": bool(row.is_active),
        "timezone_name": row.timezone_name,
        "days": [
            {
                "cycle_day_index": day.cycle_day_index,
                "shift_template_id": day.shift_template_id,
                "status": _value(day.status),
                "start_time_local": day.start_time_local,
                "end_time_local": day.end_time_local,
                "spans_next_day": bool(day.spans_next_day),
                "planned_minutes": day.planned_minutes,
            }
            for day in days
        ],
    }


def _pattern_assignment_snapshot(row: models.EmployeeWorkPatternAssignment) -> dict:
    return {
        "user_id": str(row.user_id),
        "work_pattern_id": str(row.work_pattern_id),
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
    }


def _bootstrap_audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    operation_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Write required bootstrap evidence in the same authoritative transaction."""
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before=before,
            after=after,
            correlation_id=operation_id,
            metadata={
                "module": "workforce",
                "operation": "DEFAULT_DAY_BOOTSTRAP",
                "system_owned": True,
                **(metadata or {}),
            },
        ),
    )


def bootstrap_default_day_pattern(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> hr_schemas.HrDefaultDayBootstrapResponse:
    """Create one controlled day-shift baseline and assign it only where safe."""
    from ..rostering import models as roster_models

    amo = db.query(account_models.AMO).filter(
        account_models.AMO.id == amo_id,
    ).with_for_update().one()
    timezone_name = str(amo.time_zone or "UTC")
    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()
    week_monday = today - timedelta(days=today.weekday())
    operation_id = str(uuid4())

    shift_id = _default_day_system_id(amo_id=amo_id, system_key=_DEFAULT_DAY_SHIFT_KEY)
    shift_by_code = db.query(roster_models.ShiftTemplate).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.code == _DEFAULT_DAY_SHIFT_CODE,
    ).with_for_update().first()
    shift = db.query(roster_models.ShiftTemplate).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.id == shift_id,
    ).with_for_update().first()
    if shift_by_code is not None and str(shift_by_code.id) != shift_id:
        raise ValueError(
            "Reserved shift code DEFAULT-DAY is already owned by tenant configuration; "
            "rename that shift before applying the managed default-day baseline."
        )
    if shift is not None and shift_by_code is not None and str(shift.id) != str(shift_by_code.id):
        raise ValueError("Managed default-day shift identity conflicts with the reserved code")

    shift_before = _shift_template_snapshot(shift) if shift is not None else None
    if shift is None:
        shift = roster_models.ShiftTemplate(
            id=shift_id,
            amo_id=amo_id,
            code=_DEFAULT_DAY_SHIFT_CODE,
            label="Default day shift",
            kind=roster_models.ShiftTemplateKind.DAY,
            default_start_time="08:00",
            default_end_time="17:00",
            duration_minutes=480,
            counts_as_duty=True,
            is_active=True,
            display_order=10,
            description=(
                "Portal-managed baseline for active staff without an assigned work pattern; "
                "planner review remains required."
            ),
            icon_name="Sun",
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(shift)
    else:
        shift.code = _DEFAULT_DAY_SHIFT_CODE
        shift.label = "Default day shift"
        shift.kind = roster_models.ShiftTemplateKind.DAY
        shift.default_start_time = "08:00"
        shift.default_end_time = "17:00"
        shift.duration_minutes = 480
        shift.counts_as_duty = True
        shift.is_active = True
        shift.display_order = 10
        shift.description = (
            "Portal-managed baseline for active staff without an assigned work pattern; "
            "planner review remains required."
        )
        shift.icon_name = "Sun"
        shift.updated_by_user_id = actor_user_id
        db.add(shift)
    db.flush()
    shift_after = _shift_template_snapshot(shift)
    if shift_before != shift_after:
        _bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="ShiftTemplate",
            entity_id=str(shift.id),
            action="bootstrap_create" if shift_before is None else "bootstrap_update",
            before=shift_before,
            after=shift_after,
            metadata={"system_key": _DEFAULT_DAY_SHIFT_KEY},
        )

    pattern_id = _default_day_system_id(amo_id=amo_id, system_key=_DEFAULT_DAY_PATTERN_KEY)
    pattern_by_code = db.query(models.WorkPattern).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.code == _DEFAULT_DAY_PATTERN_CODE,
    ).with_for_update().first()
    pattern = db.query(models.WorkPattern).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.id == pattern_id,
    ).with_for_update().first()
    if pattern_by_code is not None and str(pattern_by_code.id) != pattern_id:
        raise ValueError(
            "Reserved work-pattern code DEFAULT-DAY-5X2 is already owned by tenant configuration; "
            "rename that pattern before applying the managed default-day baseline."
        )
    if pattern is not None and pattern_by_code is not None and str(pattern.id) != str(pattern_by_code.id):
        raise ValueError("Managed default-day pattern identity conflicts with the reserved code")

    pattern_before = _work_pattern_snapshot(db, pattern) if pattern is not None else None
    if pattern is None:
        pattern = models.WorkPattern(
            id=pattern_id,
            amo_id=amo_id,
            code=_DEFAULT_DAY_PATTERN_CODE,
            name="Default day shift · Monday to Friday",
            description=(
                "Portal-managed five-day baseline followed by two days off. "
                "This is visible draft input, not a published roster."
            ),
            cycle_length_days=7,
            is_active=True,
            timezone_name=timezone_name,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(pattern)
        db.flush()
    else:
        pattern.code = _DEFAULT_DAY_PATTERN_CODE
        pattern.name = "Default day shift · Monday to Friday"
        pattern.description = (
            "Portal-managed five-day baseline followed by two days off. "
            "This is visible draft input, not a published roster."
        )
        pattern.cycle_length_days = 7
        pattern.is_active = True
        pattern.timezone_name = timezone_name
        pattern.updated_by_user_id = actor_user_id
        db.add(pattern)
        db.flush()

    existing_days = db.query(models.WorkPatternDay).filter(
        models.WorkPatternDay.amo_id == amo_id,
        models.WorkPatternDay.work_pattern_id == pattern.id,
    ).order_by(models.WorkPatternDay.cycle_day_index.asc(), models.WorkPatternDay.id.asc()).all()
    days_by_index = {int(row.cycle_day_index): row for row in existing_days if 0 <= int(row.cycle_day_index) < 7}
    for extra_day in existing_days:
        if int(extra_day.cycle_day_index) not in range(7):
            db.delete(extra_day)
    for day_index in range(7):
        duty = day_index < 5
        day = days_by_index.get(day_index)
        if day is None:
            day = models.WorkPatternDay(
                amo_id=amo_id,
                work_pattern_id=pattern.id,
                cycle_day_index=day_index,
            )
        day.shift_template_id = shift.id if duty else None
        day.status = models.PatternDayStatus.DUTY if duty else models.PatternDayStatus.OFF
        day.start_time_local = "08:00" if duty else None
        day.end_time_local = "17:00" if duty else None
        day.spans_next_day = False
        day.planned_minutes = 480 if duty else 0
        db.add(day)
    db.flush()
    pattern_after = _work_pattern_snapshot(db, pattern)
    if pattern_before != pattern_after:
        _bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="WorkPattern",
            entity_id=str(pattern.id),
            action="bootstrap_create" if pattern_before is None else "bootstrap_update",
            before=pattern_before,
            after=pattern_after,
            metadata={"system_key": _DEFAULT_DAY_PATTERN_KEY},
        )

    users = _active_tenant_users(db, amo_id=amo_id)
    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)
    eligible_users = [
        user for user in users
        if (contract := contracts.get(str(user.id))) is not None
        and _value(contract.employment_status) in {
            models.EmploymentStatus.ACTIVE.value,
            models.EmploymentStatus.ONBOARDING.value,
        }
    ]
    current_rows = db.query(models.EmployeeWorkPatternAssignment).options(
        joinedload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id.in_([str(user.id) for user in eligible_users] or ["__none__"]),
        models.EmployeeWorkPatternAssignment.effective_from <= today,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= today,
        ),
    ).with_for_update().all()
    occupied = {str(row.user_id): row for row in current_rows}

    assigned = 0
    already_assigned = 0
    skipped_conflict = 0
    for user in eligible_users:
        current = occupied.get(str(user.id))
        current_has_active_pattern = bool(
            current and current.work_pattern and current.work_pattern.is_active
        )
        current_is_reserved_default = bool(
            current_has_active_pattern and str(current.work_pattern_id) == str(pattern.id)
        )
        current_default_anchor_is_monday = bool(
            current_is_reserved_default
            and current.cycle_anchor_date
            and current.cycle_anchor_date.weekday() == 0
        )
        if current_has_active_pattern and (
            not current_is_reserved_default or current_default_anchor_is_monday
        ):
            already_assigned += 1
            continue

        future = db.query(models.EmployeeWorkPatternAssignment).filter(
            models.EmployeeWorkPatternAssignment.amo_id == amo_id,
            models.EmployeeWorkPatternAssignment.user_id == user.id,
            models.EmployeeWorkPatternAssignment.effective_from > today,
        ).order_by(models.EmployeeWorkPatternAssignment.effective_from.asc()).with_for_update().first()
        effective_to = future.effective_from - timedelta(days=1) if future else None
        if effective_to is not None and effective_to < today:
            skipped_conflict += 1
            continue

        if current is not None:
            current_before = _pattern_assignment_snapshot(current)
            if current.effective_from < today:
                current.effective_to = today - timedelta(days=1)
                db.add(current)
                db.flush()
                _bootstrap_audit(
                    db,
                    amo_id=amo_id,
                    actor_user_id=actor_user_id,
                    operation_id=operation_id,
                    entity_type="EmployeeWorkPatternAssignment",
                    entity_id=str(current.id),
                    action="bootstrap_close",
                    before=current_before,
                    after=_pattern_assignment_snapshot(current),
                    metadata={"user_id": str(user.id), "replacement_pattern_id": str(pattern.id)},
                )
            else:
                current_id = str(current.id)
                db.delete(current)
                db.flush()
                _bootstrap_audit(
                    db,
                    amo_id=amo_id,
                    actor_user_id=actor_user_id,
                    operation_id=operation_id,
                    entity_type="EmployeeWorkPatternAssignment",
                    entity_id=current_id,
                    action="bootstrap_delete",
                    before=current_before,
                    after=None,
                    metadata={"user_id": str(user.id), "replacement_pattern_id": str(pattern.id)},
                )

        created = models.EmployeeWorkPatternAssignment(
            amo_id=amo_id,
            user_id=user.id,
            work_pattern_id=pattern.id,
            effective_from=today,
            effective_to=effective_to,
            cycle_anchor_date=week_monday,
            created_by_user_id=actor_user_id,
        )
        db.add(created)
        db.flush()
        _bootstrap_audit(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            entity_type="EmployeeWorkPatternAssignment",
            entity_id=str(created.id),
            action="bootstrap_assign",
            after=_pattern_assignment_snapshot(created),
            metadata={"user_id": str(user.id), "system_key": _DEFAULT_DAY_PATTERN_KEY},
        )
        assigned += 1

    db.flush()
    return hr_schemas.HrDefaultDayBootstrapResponse(
        shift_template_id=shift.id,
        work_pattern_id=pattern.id,
        eligible_user_count=len(eligible_users),
        assigned_user_count=assigned,
        already_assigned_count=already_assigned,
        skipped_conflict_count=skipped_conflict,
    )
'''
service_path.write_text(service_text[:start] + new_block + "\n", encoding="utf-8")

# Strengthen source contracts for provenance, collision refusal and transactional audit evidence.
test_path = ROOT / "backend/amodb/apps/workforce/tests/test_hr_review_flags.py"
test_text = test_path.read_text(encoding="utf-8")
addition = r'''


def test_default_day_bootstrap_refuses_unowned_reserved_codes_and_uses_owned_ids():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    identity_source = inspect.getsource(hr_service._default_day_system_id)
    assert "uuid5" in identity_source
    assert "amo-portal:{amo_id}:{system_key}" in identity_source
    assert "shift_by_code" in source
    assert "pattern_by_code" in source
    assert "already owned by tenant configuration" in source
    assert "id=shift_id" in source
    assert "id=pattern_id" in source
    assert "current.work_pattern_id" in source
    assert "current.work_pattern.code" not in source


def test_default_day_bootstrap_audits_every_controlled_mutation():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    audit_source = inspect.getsource(hr_service._bootstrap_audit)
    assert "create_audit_event" in audit_source
    assert "correlation_id=operation_id" in audit_source
    assert '"system_owned": True' in audit_source
    for action in (
        'action="bootstrap_create"',
        'action="bootstrap_update"',
        'action="bootstrap_close"',
        'action="bootstrap_delete"',
        'action="bootstrap_assign"',
    ):
        assert action in source
    assert 'entity_type="ShiftTemplate"' in source
    assert 'entity_type="WorkPattern"' in source
    assert 'entity_type="EmployeeWorkPatternAssignment"' in source
    assert "before=current_before" in source
    assert "after=_pattern_assignment_snapshot" in source
'''
if "test_default_day_bootstrap_refuses_unowned_reserved_codes_and_uses_owned_ids" not in test_text:
    test_path.write_text(test_text.rstrip() + addition + "\n", encoding="utf-8")

# Record the new governance invariants.
doc_path = ROOT / "backend/docs/rostering/WORKFORCE_ACTIVE_USER_READINESS_20260729.md"
doc = doc_path.read_text(encoding="utf-8")
needle = "- The resize grip is rendered with CSS rather than a separate icon chunk, preserving the visual control without adding a request to the Rostering planner's synthetic 2G waterfall.\n"
replacement = needle + "- Reserved default-day definitions use deterministic tenant-scoped portal identities; a tenant-authored record using either reserved code causes an explicit collision error and is never rewritten.\n- Every actual bootstrap definition or assignment mutation writes an append-only AuditEvent with the actor, before/after state, and one correlation ID inside the same transaction.\n"
if needle not in doc:
    raise RuntimeError("documentation governance anchor missing")
doc_path.write_text(doc.replace(needle, replacement, 1), encoding="utf-8")

print("PR377 bootstrap provenance and audit governance applied")
