from __future__ import annotations

from sqlalchemy.orm import Session

from ..rostering import models as roster_models
from . import models as workforce_models


def _canonical_rd(db: Session, *, amo_id: str) -> roster_models.ShiftTemplate:
    row = db.query(roster_models.ShiftTemplate).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.code == "RD",
        roster_models.ShiftTemplate.is_active.is_(True),
        roster_models.ShiftTemplate.kind == roster_models.ShiftTemplateKind.OFF,
        roster_models.ShiftTemplate.counts_as_duty.is_(False),
    ).first()
    if row is None:
        raise ValueError("Canonical RD shift template is required before saving protected OFF days")
    return row


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
    rd = _canonical_rd(db, amo_id=amo_id)
    normalized = [
        day.model_copy(
            update={
                "shift_template_id": rd.id,
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
