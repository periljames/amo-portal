"""Tenant-safe scheduler for the monthly expiry-driven training plan.

The HTTP endpoint remains the explicit/manual trigger. This runner executes the
same governed service only for configured tenants whose local run time is due;
the service's monthly idempotency key prevents duplicate plan materialisation
when more than one worker process is deployed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import desc

from amodb.apps.accounts import models as account_models
from amodb.apps.training import operating_models as models
from amodb.apps.training import operating_service as service
from amodb.database import WriteSessionLocal, close_session_safely


logger = logging.getLogger(__name__)
UTC = timezone.utc


def _tenant_now(timezone_name: str | None, now: datetime) -> datetime:
    name = (timezone_name or "UTC").strip() or "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Invalid training automation timezone %r; using UTC", name)
        zone = UTC
    aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return aware.astimezone(zone)


def _is_due(settings: models.TrainingOperatingSettings, now: datetime) -> tuple[bool, datetime]:
    local_now = _tenant_now(settings.timezone, now)
    run_day = max(1, min(int(settings.plan_run_day or 1), 28))
    run_hour = max(0, min(int(settings.plan_run_hour or 0), 23))
    return (local_now.day, local_now.hour) >= (run_day, run_hour), local_now


def _automation_actor(db: Any, settings: models.TrainingOperatingSettings) -> account_models.User | None:
    base = db.query(account_models.User).filter(
        account_models.User.amo_id == settings.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if settings.updated_by_user_id:
        configured_by = base.filter(account_models.User.id == settings.updated_by_user_id).first()
        if configured_by is not None:
            return configured_by
    return base.order_by(
        desc(account_models.User.is_amo_admin),
        desc(account_models.User.is_superuser),
        account_models.User.id.asc(),
    ).first()


def run_once(*, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
    """Run every due tenant at most once for its current local month."""
    clock = now or datetime.now(UTC)
    db = WriteSessionLocal()
    summary = {
        "configured": 0,
        "due": 0,
        "completed": 0,
        "action_required": 0,
        "already_run": 0,
        "not_due": 0,
        "no_actor": 0,
        "failed": 0,
    }
    try:
        settings_rows = (
            db.query(models.TrainingOperatingSettings)
            .filter(models.TrainingOperatingSettings.plan_automation_enabled.is_(True))
            .order_by(models.TrainingOperatingSettings.amo_id.asc())
            .limit(max(1, min(int(limit), 1000)))
            .all()
        )
        summary["configured"] = len(settings_rows)
        for settings in settings_rows:
            due, local_now = _is_due(settings, clock)
            if not due:
                summary["not_due"] += 1
                continue
            summary["due"] += 1
            idempotency_key = f"monthly-plan:{local_now.year:04d}-{local_now.month:02d}"
            existing = db.query(models.TrainingAutomationRun.id).filter(
                models.TrainingAutomationRun.amo_id == settings.amo_id,
                models.TrainingAutomationRun.idempotency_key == idempotency_key,
            ).first()
            if existing is not None:
                summary["already_run"] += 1
                continue
            actor = _automation_actor(db, settings)
            if actor is None:
                summary["no_actor"] += 1
                logger.warning("Training plan automation skipped tenant %s: no active human actor", settings.amo_id)
                continue
            try:
                run = service.run_monthly_plan_automation(
                    db,
                    actor=actor,
                    period=local_now.date(),
                    trigger="SCHEDULED",
                )
                db.commit()
            except Exception:
                db.rollback()
                summary["failed"] += 1
                logger.exception("Training plan automation failed for tenant %s", settings.amo_id)
                continue
            if run.status == "COMPLETED":
                summary["completed"] += 1
            elif run.status == "ACTION_REQUIRED":
                summary["action_required"] += 1
            elif run.status == "FAILED":
                summary["failed"] += 1
            else:
                summary["failed"] += 1
                logger.error("Training plan automation returned unexpected status %s", run.status)
        return summary
    finally:
        close_session_safely(db)
