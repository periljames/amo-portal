from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime import models as realtime_models
from amodb.apps.notifications import service as notification_service

from . import reminder_models as reminder_models
from . import reminder_service as service
from . import retention_models as retention_models


_installed = False
_original_collect_candidates = service._collect_candidates


def _claim_delivery(
    db: Session,
    *,
    amo_id: str,
    candidate: service.ReminderCandidate,
    recipient_user_id: str,
    stage: str,
    now: datetime,
) -> reminder_models.DocumentReminderDelivery | None:
    row = reminder_models.DocumentReminderDelivery(
        tenant_id=amo_id,
        manual_id=candidate.manual_id,
        obligation_type=candidate.obligation_type,
        obligation_id=candidate.obligation_id,
        recipient_user_id=recipient_user_id,
        reminder_stage=stage,
        due_at=candidate.due_at,
        action_url=candidate.action_url,
        delivery_json={"portal": "PENDING", "email": "PENDING"},
        sent_at=None,
        created_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return None
    return row


def _deliver(
    db: Session,
    *,
    amo_id: str,
    user: account_models.User,
    candidate: service.ReminderCandidate,
    stage: str,
    title: str,
    body: str,
    policy,
    now: datetime,
) -> bool:
    if service._already_processed(
        db,
        amo_id=amo_id,
        candidate=candidate,
        recipient_user_id=str(user.id),
        stage=stage,
    ):
        return False

    row = _claim_delivery(
        db,
        amo_id=amo_id,
        candidate=candidate,
        recipient_user_id=str(user.id),
        stage=stage,
        now=now,
    )
    if row is None:
        return False

    dedupe_key = service._notification_dedupe_key(
        amo_id=amo_id,
        candidate=candidate,
        recipient_user_id=str(user.id),
        stage=stage,
    )
    delivery: dict[str, str | None] = {"portal": "DISABLED", "email": "DISABLED"}
    error_text: str | None = None

    if policy.portal_notifications_enabled and service._portal_allowed(db, amo_id=amo_id, user_id=str(user.id)):
        existing = (
            db.query(realtime_models.PortalNotification)
            .filter(
                realtime_models.PortalNotification.amo_id == amo_id,
                realtime_models.PortalNotification.user_id == str(user.id),
                realtime_models.PortalNotification.dedupe_key == dedupe_key,
            )
            .first()
        )
        if not existing:
            db.add(realtime_models.PortalNotification(
                amo_id=amo_id,
                user_id=str(user.id),
                kind="DOCUMENT_CONTROL_REMINDER",
                title=title[:255],
                body=body[:1000],
                entity_type=candidate.obligation_type.lower(),
                entity_id=candidate.obligation_id,
                action_url=candidate.action_url,
                dedupe_key=dedupe_key,
                metadata_json={
                    "manual_id": candidate.manual_id,
                    "obligation_type": candidate.obligation_type,
                    "reminder_stage": stage,
                    "due_at": candidate.due_at.isoformat(),
                },
            ))
        delivery["portal"] = "QUEUED"
    elif policy.portal_notifications_enabled:
        delivery["portal"] = "SKIPPED_BY_PREFERENCE"

    if policy.email_notifications_enabled:
        try:
            email_log = notification_service.send_email(
                "document-control-reminder",
                user.email,
                title,
                {
                    "title": title,
                    "message": body,
                    "action_url": candidate.action_url,
                    "obligation_type": candidate.obligation_type,
                    "due_at": candidate.due_at.isoformat(),
                },
                dedupe_key,
                critical=False,
                amo_id=amo_id,
                db=db,
                recipient_user_id=str(user.id),
                audit_context={
                    "purpose": "document-control-reminder",
                    "obligation_type": candidate.obligation_type,
                    "obligation_id": candidate.obligation_id,
                    "reminder_stage": stage,
                },
            )
            delivery["email"] = str(getattr(email_log.status, "value", email_log.status))
        except Exception as exc:
            delivery["email"] = "FAILED"
            error_text = str(exc)[:2000]

    row.delivery_json = delivery
    row.error_text = error_text
    row.sent_at = now
    db.flush()
    return True


def _collect_candidates(db: Session, *, tenant, amo, now: datetime):
    candidates = list(_original_collect_candidates(db, tenant=tenant, amo=amo, now=now))
    zone = service._local_zone(amo)
    today = now.astimezone(zone).date()
    manuals = {
        row.id: row
        for row in db.query(service.manual_models.Manual)
        .filter(service.manual_models.Manual.tenant_id == tenant.id)
        .all()
    }
    rows = (
        db.query(retention_models.DocumentRetentionDisposition)
        .filter(
            retention_models.DocumentRetentionDisposition.tenant_id == tenant.amo_id,
            retention_models.DocumentRetentionDisposition.status.in_(["ACTIVE", "DUE", "REJECTED"]),
            retention_models.DocumentRetentionDisposition.legal_hold.is_(False),
            retention_models.DocumentRetentionDisposition.retention_until.isnot(None),
        )
        .all()
    )
    for row in rows:
        manual = manuals.get(row.manual_id)
        if not manual or not row.retention_until:
            continue
        recipient = row.created_by_user_id or service._profile_owner(
            db,
            amo_id=tenant.amo_id,
            manual_id=row.manual_id,
        )
        due = service._as_due_datetime(row.retention_until, zone)
        phrase = service._due_phrase(due_date=due.astimezone(zone).date(), today=today)
        candidates.append(service._candidate(
            obligation_type="RETENTION_DUE",
            obligation_id=row.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=recipient,
            due_at=due,
            title=f"Document retention review due · {manual.code}",
            body=(
                f"Retention governance for {row.source_label} is {phrase}. "
                "Review legal hold and request controlled disposition when appropriate."
            ),
            action_suffix=f"/library/{manual.id}?tab=overview&retention={row.id}",
        ))
    return candidates


def install() -> None:
    global _installed
    if _installed:
        return
    service._deliver = _deliver
    service._collect_candidates = _collect_candidates
    _installed = True
