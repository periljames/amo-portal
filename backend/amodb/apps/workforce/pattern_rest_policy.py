from __future__ import annotations

from sqlalchemy.orm import Session

from ..rostering import models as roster_models
from ..rostering.code_registry import normalize_shift_code
from . import models as workforce_models


def _canonical_rd_id(db: Session, *, amo_id: str) -> str:
    rows = db.query(roster_models.ShiftTemplate).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.is_active.is_(True),
        roster_models.ShiftTemplate.kind == roster_models.ShiftTemplateKind.OFF,
        roster_models.ShiftTemplate.counts_as_duty.is_(False),
    ).order_by(roster_models.ShiftTemplate.code.asc()).all()
    # Existing tenants use O/OF/RR. Reuse their protected-rest template rather
    # than requiring a destructive rename or creating another shift code.
    row = next((item for item in rows if item.code == "RD"), None)
    if row is None:
        row = next((item for item in rows if normalize_shift_code(item.code) == "RD"), None)
    if row is None and len(rows) == 1:
        row = rows[0]
    if row is None:
        raise ValueError("Configure an active Off duty shift in Setup > Shifts & patterns (RD or O), with Counts as duty disabled, then save the rotation again.")
    return str(row.id)


def canonicalize_pattern_payload(db: Session, *, amo_id: str, payload):
    days = getattr(payload, "days", None)
    if days is None:
        return payload
    needs_rd = any(
        day.status == workforce_models.PatternDayStatus.OFF and not day.shift_template_id
        for day in days
    )
    if not needs_rd:
        return payload
    rd_id = _canonical_rd_id(db, amo_id=amo_id)
    normalized = [
        day.model_copy(
            update={
                "shift_template_id": rd_id,
                "start_time_local": None,
                "end_time_local": None,
                "spans_next_day": False,
                "planned_minutes": 0,
            }
        )
        if day.status == workforce_models.PatternDayStatus.OFF and not day.shift_template_id
        else day
        for day in days
    ]
    return payload.model_copy(update={"days": normalized})


def install_service_policy(service_module) -> None:
    if getattr(service_module, "_canonical_rd_pattern_policy_installed", False):
        return
    original_create = service_module.create_pattern
    original_update = service_module.update_pattern

    def governed_create(db: Session, *, amo_id: str, actor_user_id: str, payload):
        payload = canonicalize_pattern_payload(db, amo_id=amo_id, payload=payload)
        return original_create(db, amo_id=amo_id, actor_user_id=actor_user_id, payload=payload)

    def governed_update(db: Session, *, row, actor_user_id: str, payload):
        payload = canonicalize_pattern_payload(db, amo_id=row.amo_id, payload=payload)
        return original_update(db, row=row, actor_user_id=actor_user_id, payload=payload)

    service_module.create_pattern = governed_create
    service_module.update_pattern = governed_update
    service_module._canonical_rd_pattern_policy_installed = True
