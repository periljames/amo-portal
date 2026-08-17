"""Tenant-safe scheduled Training compliance notifications.

This job creates durable, deduplicated in-app actions from the authoritative
Training compliance engine. External delivery remains a separate channel concern;
this scheduler never marks an email/WhatsApp message as delivered merely because
an in-app notification was created.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError

from amodb.apps.accounts import models as account_models
from amodb.apps.training import compliance
from amodb.apps.training import models as training_models
from amodb.apps.training import operating_models
from amodb.database import WriteSessionLocal, close_session_safely


logger = logging.getLogger(__name__)
UTC = timezone.utc
_DEFAULT_DUE_DAYS = (90, 60, 30, 15, 7, 1)
_DEFAULT_OVERDUE_DAYS = (1, 7, 14, 30)


@dataclass(frozen=True)
class ReminderPolicy:
    enabled: bool
    due_days: tuple[int, ...]
    overdue_days: tuple[int, ...]


def _positive_unique_days(value: Any, default: Iterable[int]) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple, set)):
        value = default
    result: set[int] = set()
    for raw in value:
        try:
            day = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 730:
            result.add(day)
    return tuple(sorted(result, reverse=True)) or tuple(sorted(set(default), reverse=True))


def reminder_policy(raw: Any) -> ReminderPolicy:
    payload = raw if isinstance(raw, dict) else {}
    reminders = payload.get("compliance_reminders") if isinstance(payload.get("compliance_reminders"), dict) else payload
    enabled = reminders.get("enabled", True) is not False
    return ReminderPolicy(
        enabled=enabled,
        due_days=_positive_unique_days(reminders.get("due_days"), _DEFAULT_DUE_DAYS),
        overdue_days=_positive_unique_days(reminders.get("overdue_days"), _DEFAULT_OVERDUE_DAYS),
    )


def selected_milestone(days_until_due: int | None, policy: ReminderPolicy) -> tuple[str, int] | None:
    """Return the single most relevant crossed reminder milestone.

    Choosing one milestone avoids a burst of historical reminders when a tenant
    first enables the scheduler. The due-date-specific dedupe key makes repeated
    hourly runs idempotent.
    """

    if days_until_due is None:
        return None
    days = int(days_until_due)
    if days >= 0:
        candidates = [threshold for threshold in policy.due_days if days <= threshold]
        if not candidates:
            return None
        return "DUE", min(candidates)
    overdue = abs(days)
    candidates = [threshold for threshold in policy.overdue_days if overdue >= threshold]
    if not candidates:
        return None
    return "OVERDUE", max(candidates)


def _tenant_date(settings: operating_models.TrainingOperatingSettings, now: datetime) -> date:
    timezone_name = (settings.timezone or "UTC").strip() or "UTC"
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Invalid Training notification timezone %r for tenant %s; using UTC", timezone_name, settings.amo_id)
        zone = UTC
    aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return aware.astimezone(zone).date()


def _link_path(amo: account_models.AMO, course_id: str) -> str:
    tenant = str(amo.login_slug or amo.amo_code or amo.id)
    return f"/maintenance/{tenant}/training?course={course_id}"


def _notification_for_item(
    *,
    amo: account_models.AMO,
    user: account_models.User,
    item: Any,
    milestone: tuple[str, int],
) -> training_models.TrainingNotification:
    state, threshold = milestone
    due_date = item.extended_due_date or item.valid_until
    due_key = due_date.isoformat() if due_date else "no-due-date"
    course_id = str(item.course_id)
    if state == "OVERDUE":
        title = f"Training overdue: {item.course_name}"
        body = f"{item.course_name} is overdue. Open My Training to resolve the requirement or follow the permitted deferral path."
        severity = training_models.TrainingNotificationSeverity.ACTION_REQUIRED
    else:
        title = f"Training due in {abs(int(item.days_until_due or 0))} day(s): {item.course_name}"
        body = f"{item.course_name} is due on {due_key}. Open My Training to review the requirement and any planned session."
        severity = training_models.TrainingNotificationSeverity.WARNING
    return training_models.TrainingNotification(
        amo_id=str(user.amo_id),
        user_id=str(user.id),
        title=title,
        body=body,
        severity=severity,
        link_path=_link_path(amo, course_id),
        dedupe_key=f"compliance:{course_id}:{due_key}:{state}:{threshold}",
        created_by_user_id=None,
    )


def run_once(*, now: datetime | None = None, tenant_limit: int = 100, user_limit_per_tenant: int = 5000) -> dict[str, int]:
    clock = now or datetime.now(UTC)
    db = WriteSessionLocal()
    summary = {
        "configured": 0,
        "enabled": 0,
        "users_evaluated": 0,
        "created": 0,
        "deduped": 0,
        "disabled": 0,
        "failed_tenants": 0,
    }
    try:
        settings_rows = (
            db.query(operating_models.TrainingOperatingSettings)
            .order_by(operating_models.TrainingOperatingSettings.amo_id.asc())
            .limit(max(1, min(int(tenant_limit), 1000)))
            .all()
        )
        summary["configured"] = len(settings_rows)
        for settings in settings_rows:
            policy = reminder_policy(settings.notification_policy)
            if not policy.enabled:
                summary["disabled"] += 1
                continue
            summary["enabled"] += 1
            today = _tenant_date(settings, clock)
            try:
                amo = db.query(account_models.AMO).filter(
                    account_models.AMO.id == settings.amo_id,
                    account_models.AMO.is_active.is_(True),
                ).first()
                if amo is None:
                    continue
                users = (
                    db.query(account_models.User)
                    .filter(
                        account_models.User.amo_id == settings.amo_id,
                        account_models.User.is_active.is_(True),
                        account_models.User.is_system_account.is_(False),
                    )
                    .order_by(account_models.User.id.asc())
                    .limit(max(1, min(int(user_limit_per_tenant), 20_000)))
                    .all()
                )
                for user in users:
                    evaluation = compliance.evaluate_user_training_policy(db, user, required_only=True, today=today)
                    summary["users_evaluated"] += 1
                    for item in evaluation.mandatory_items:
                        if item.status not in {"DUE_SOON", "OVERDUE"}:
                            continue
                        milestone = selected_milestone(item.days_until_due, policy)
                        if milestone is None:
                            continue
                        notification = _notification_for_item(amo=amo, user=user, item=item, milestone=milestone)
                        existing = db.query(training_models.TrainingNotification.id).filter(
                            training_models.TrainingNotification.amo_id == notification.amo_id,
                            training_models.TrainingNotification.user_id == notification.user_id,
                            training_models.TrainingNotification.dedupe_key == notification.dedupe_key,
                        ).first()
                        if existing is not None:
                            summary["deduped"] += 1
                            continue
                        try:
                            with db.begin_nested():
                                db.add(notification)
                                db.flush()
                        except IntegrityError:
                            # Concurrent workers are protected by the database
                            # unique constraint without rolling back other tenant
                            # notifications already created in this transaction.
                            summary["deduped"] += 1
                            continue
                        summary["created"] += 1
                db.commit()
            except Exception:
                db.rollback()
                summary["failed_tenants"] += 1
                logger.exception("Training notification automation failed for tenant %s", settings.amo_id)

        try:
            from amodb.apps.training.workflow_completion import run_workflow_escalations

            workflow_summary = run_workflow_escalations(db, now=clock)
            db.commit()
            for key, value in workflow_summary.items():
                summary[f"workflow_{key}"] = int(value)
        except Exception:
            db.rollback()
            summary["errors"] += 1
            logger.exception("Training workflow escalation pass failed")

        return summary
    finally:
        close_session_safely(db)


__all__ = ["ReminderPolicy", "reminder_policy", "run_once", "selected_milestone"]
