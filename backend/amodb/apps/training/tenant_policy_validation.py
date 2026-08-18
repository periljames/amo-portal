from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..accounts import models as account_models

_ALLOWED_CHANNELS = {"EMAIL", "WHATSAPP"}
_ALLOWED_DELIVERY_MODES = {"PARALLEL", "FALLBACK"}


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _positive_day_list(value: Any, *, field: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail=f"notification_policy.{field} must be a list of tenant-defined day milestones.")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise HTTPException(status_code=422, detail=f"notification_policy.{field} contains an invalid day value.")
        try:
            day = int(item)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"notification_policy.{field} contains an invalid day value.") from exc
        if day < 1 or day > 730:
            raise HTTPException(status_code=422, detail=f"notification_policy.{field} day values must be between 1 and 730.")
        result.append(day)
    return sorted(set(result), reverse=True)


def _bounded_int(value: Any, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise HTTPException(status_code=422, detail=f"notification_policy.delivery.{field} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"notification_policy.delivery.{field} is required and must be an integer.") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(status_code=422, detail=f"notification_policy.delivery.{field} must be between {minimum} and {maximum}.")
    return parsed


def validate_notification_policy(db: Session, *, amo_id: str, raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="notification_policy must be an object.")
    policy = dict(raw)

    reminders = policy.get("compliance_reminders")
    if reminders is not None and not isinstance(reminders, dict):
        raise HTTPException(status_code=422, detail="notification_policy.compliance_reminders must be an object.")
    if isinstance(reminders, dict):
        due_days = _positive_day_list(reminders.get("due_days"), field="compliance_reminders.due_days")
        overdue_days = _positive_day_list(reminders.get("overdue_days"), field="compliance_reminders.overdue_days")
        if reminders.get("enabled") is True and not due_days and not overdue_days:
            raise HTTPException(status_code=422, detail="Enabled compliance reminders require at least one tenant-defined due or overdue milestone.")
        policy["compliance_reminders"] = {**reminders, "due_days": due_days, "overdue_days": overdue_days}

    raw_channels = policy.get("external_channels") or []
    if not isinstance(raw_channels, list):
        raise HTTPException(status_code=422, detail="notification_policy.external_channels must be a list.")
    channels = list(dict.fromkeys(str(item).strip().upper() for item in raw_channels if str(item).strip()))
    unsupported = [item for item in channels if item not in _ALLOWED_CHANNELS]
    if unsupported:
        raise HTTPException(status_code=422, detail={"message": "Unsupported Training notification channel.", "channels": unsupported})
    policy["external_channels"] = channels

    delivery = policy.get("delivery")
    if delivery is not None and not isinstance(delivery, dict):
        raise HTTPException(status_code=422, detail="notification_policy.delivery must be an object.")
    delivery_payload = _object(delivery)
    if delivery_payload.get("enabled") is True:
        if not channels:
            raise HTTPException(status_code=422, detail="External delivery cannot be enabled until this tenant selects at least one delivery channel.")
        mode = str(delivery_payload.get("mode") or "").strip().upper()
        if mode not in _ALLOWED_DELIVERY_MODES:
            raise HTTPException(status_code=422, detail="notification_policy.delivery.mode must be PARALLEL or FALLBACK.")
        attempts = _bounded_int(delivery_payload.get("max_attempts"), field="max_attempts", minimum=1, maximum=20)
        base_seconds = _bounded_int(delivery_payload.get("retry_base_seconds"), field="retry_base_seconds", minimum=1, maximum=86400)
        ceiling_seconds = _bounded_int(delivery_payload.get("retry_ceiling_seconds"), field="retry_ceiling_seconds", minimum=1, maximum=604800)
        if ceiling_seconds < base_seconds:
            raise HTTPException(status_code=422, detail="notification_policy.delivery.retry_ceiling_seconds cannot be lower than retry_base_seconds.")
        escalation_ids = delivery_payload.get("escalation_user_ids") or []
        if not isinstance(escalation_ids, list):
            raise HTTPException(status_code=422, detail="notification_policy.delivery.escalation_user_ids must be a list.")
        normalized_ids = list(dict.fromkeys(str(item).strip() for item in escalation_ids if str(item).strip()))
        if normalized_ids:
            rows = db.query(account_models.User.id).filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id.in_(normalized_ids),
                account_models.User.is_active.is_(True),
            ).all()
            found = {str(row[0]) for row in rows}
            missing = [user_id for user_id in normalized_ids if user_id not in found]
            if missing:
                raise HTTPException(status_code=422, detail={"message": "One or more Training delivery escalation recipients are not active users in this tenant.", "user_ids": missing})
        policy["delivery"] = {
            **delivery_payload,
            "enabled": True,
            "mode": mode,
            "max_attempts": attempts,
            "retry_base_seconds": base_seconds,
            "retry_ceiling_seconds": ceiling_seconds,
            "escalation_user_ids": normalized_ids,
        }
    elif delivery is not None:
        policy["delivery"] = {**delivery_payload, "enabled": False}

    return policy


def wrap_update_settings(base_update: Callable):
    def update_settings(db: Session, *, amo_id: str, payload, actor_user_id: str | None):
        values = payload.model_dump(exclude_unset=True)
        if "notification_policy" in values:
            normalized = validate_notification_policy(db, amo_id=amo_id, raw=values.get("notification_policy"))
            payload = payload.model_copy(update={"notification_policy": normalized})
        return base_update(db, amo_id=amo_id, payload=payload, actor_user_id=actor_user_id)

    return update_settings


__all__ = ["validate_notification_policy", "wrap_update_settings"]
