from __future__ import annotations

import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.notifications import service as notification_service
from amodb.apps.realtime import models as realtime_models
from amodb.database import WriteSessionLocal, close_session_safely

from . import domain_models as dm
from . import reminder_models as rm
from .reminder_policy import DocumentReminderPolicy, reminder_policy_from_settings


logger = logging.getLogger(__name__)
REMINDER_INTERVAL_SECONDS = max(900, min(int(os.getenv("DOCUMENT_CONTROL_REMINDER_INTERVAL_SECONDS", "3600")), 86400))
_ADVISORY_LOCK_KEY = int.from_bytes(hashlib.sha256(b"document-control-reminder-cycle").digest()[:8], "big", signed=False) & 0x7FFF_FFFF_FFFF_FFFF
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


@dataclass(frozen=True)
class ReminderCandidate:
    obligation_type: str
    obligation_id: str
    manual_id: str
    recipient_user_id: str | None
    due_at: datetime
    title: str
    body: str
    action_url: str


def _local_zone(amo: account_models.AMO) -> ZoneInfo:
    try:
        return ZoneInfo(str(amo.time_zone or "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def _as_due_datetime(value: datetime | date, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    local = datetime.combine(value, time(hour=23, minute=59, second=59), tzinfo=zone)
    return local.astimezone(timezone.utc)


def reminder_stage(*, due_date: date, today: date, policy: DocumentReminderPolicy) -> str | None:
    days_until = (due_date - today).days
    if days_until > max(policy.lead_days):
        return None
    if days_until > 0:
        eligible = [lead for lead in policy.lead_days if days_until <= lead]
        return f"DUE_{min(eligible)}" if eligible else None
    if days_until == 0:
        return "DUE_TODAY"
    overdue_days = abs(days_until)
    bucket = ((overdue_days - 1) // policy.overdue_repeat_days) + 1
    return f"OVERDUE_W{bucket}"


def _days_overdue(*, due_date: date, today: date) -> int:
    return max(0, (today - due_date).days)


def _due_phrase(*, due_date: date, today: date) -> str:
    delta = (due_date - today).days
    if delta > 1:
        return f"in {delta} days"
    if delta == 1:
        return "tomorrow"
    if delta == 0:
        return "today"
    overdue = abs(delta)
    return f"{overdue} day{'s' if overdue != 1 else ''} overdue"


def _active_user(db: Session, *, amo_id: str, user_id: str | None) -> account_models.User | None:
    if not user_id:
        return None
    return (
        db.query(account_models.User)
        .filter(
            account_models.User.id == user_id,
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .first()
    )


def _profile_owner(db: Session, *, amo_id: str, manual_id: str) -> str | None:
    row = (
        db.query(dm.DocumentControlProfile.owner_user_id)
        .filter(
            dm.DocumentControlProfile.tenant_id == amo_id,
            dm.DocumentControlProfile.manual_id == manual_id,
        )
        .first()
    )
    return str(row[0]) if row and row[0] else None


def _quality_escalation_user(db: Session, *, amo_id: str) -> str | None:
    for role in (account_models.AccountRole.QUALITY_MANAGER, account_models.AccountRole.AMO_ADMIN):
        row = (
            db.query(account_models.User.id)
            .filter(
                account_models.User.amo_id == amo_id,
                account_models.User.is_active.is_(True),
                account_models.User.is_system_account.is_(False),
                account_models.User.role == role,
            )
            .order_by(account_models.User.created_at.asc(), account_models.User.id.asc())
            .first()
        )
        if row:
            return str(row[0])
    return None


def _portal_allowed(db: Session, *, amo_id: str, user_id: str) -> bool:
    preference = (
        db.query(realtime_models.NotificationPreference)
        .filter(
            realtime_models.NotificationPreference.amo_id == amo_id,
            realtime_models.NotificationPreference.user_id == user_id,
        )
        .first()
    )
    return True if preference is None else bool(preference.in_app_enabled)


def _notification_dedupe_key(*, amo_id: str, candidate: ReminderCandidate, recipient_user_id: str, stage: str) -> str:
    return f"docctl:{amo_id}:{candidate.obligation_type}:{candidate.obligation_id}:{recipient_user_id}:{stage}"[:255]


def _already_processed(
    db: Session,
    *,
    amo_id: str,
    candidate: ReminderCandidate,
    recipient_user_id: str,
    stage: str,
) -> bool:
    return (
        db.query(rm.DocumentReminderDelivery.id)
        .filter(
            rm.DocumentReminderDelivery.tenant_id == amo_id,
            rm.DocumentReminderDelivery.obligation_type == candidate.obligation_type,
            rm.DocumentReminderDelivery.obligation_id == candidate.obligation_id,
            rm.DocumentReminderDelivery.recipient_user_id == recipient_user_id,
            rm.DocumentReminderDelivery.reminder_stage == stage,
        )
        .first()
        is not None
    )


def _deliver(
    db: Session,
    *,
    amo_id: str,
    user: account_models.User,
    candidate: ReminderCandidate,
    stage: str,
    title: str,
    body: str,
    policy: DocumentReminderPolicy,
    now: datetime,
) -> bool:
    if _already_processed(
        db,
        amo_id=amo_id,
        candidate=candidate,
        recipient_user_id=str(user.id),
        stage=stage,
    ):
        return False

    dedupe_key = _notification_dedupe_key(
        amo_id=amo_id,
        candidate=candidate,
        recipient_user_id=str(user.id),
        stage=stage,
    )
    delivery: dict[str, str | None] = {"portal": "DISABLED", "email": "DISABLED"}
    error_text: str | None = None

    if policy.portal_notifications_enabled and _portal_allowed(db, amo_id=amo_id, user_id=str(user.id)):
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
        except Exception as exc:  # best-effort email; portal reminder remains authoritative
            delivery["email"] = "FAILED"
            error_text = str(exc)[:2000]

    row = rm.DocumentReminderDelivery(
        tenant_id=amo_id,
        manual_id=candidate.manual_id,
        obligation_type=candidate.obligation_type,
        obligation_id=candidate.obligation_id,
        recipient_user_id=str(user.id),
        reminder_stage=stage,
        due_at=candidate.due_at,
        action_url=candidate.action_url,
        delivery_json=delivery,
        error_text=error_text,
        sent_at=now,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def _candidate(
    *,
    obligation_type: str,
    obligation_id: str,
    manual: manual_models.Manual,
    tenant: manual_models.Tenant,
    recipient_user_id: str | None,
    due_at: datetime,
    title: str,
    body: str,
    action_suffix: str,
) -> ReminderCandidate:
    base = f"/maintenance/{tenant.slug}/document-control"
    return ReminderCandidate(
        obligation_type=obligation_type,
        obligation_id=obligation_id,
        manual_id=manual.id,
        recipient_user_id=recipient_user_id,
        due_at=due_at,
        title=title,
        body=body,
        action_url=f"{base}{action_suffix}",
    )


def _collect_candidates(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    amo: account_models.AMO,
    now: datetime,
) -> list[ReminderCandidate]:
    zone = _local_zone(amo)
    today = now.astimezone(zone).date()
    manuals = {
        row.id: row
        for row in db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id).all()
    }
    candidates: list[ReminderCandidate] = []

    reviews = (
        db.query(dm.DocumentReviewPlan)
        .filter(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]),
            dm.DocumentReviewPlan.owner_user_id.isnot(None),
        )
        .all()
    )
    for row in reviews:
        manual = manuals.get(row.manual_id)
        if not manual:
            continue
        due = _as_due_datetime(row.due_at, zone)
        phrase = _due_phrase(due_date=due.astimezone(zone).date(), today=today)
        candidates.append(_candidate(
            obligation_type="PERIODIC_REVIEW",
            obligation_id=row.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=row.owner_user_id,
            due_at=due,
            title=f"Document review due · {manual.code}",
            body=f"The periodic review for {manual.code} — {manual.title} is {phrase}.",
            action_suffix=f"/library/{manual.id}?tab=compliance",
        ))

    trs = (
        db.query(dm.DocumentTemporaryRevision)
        .filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
            dm.DocumentTemporaryRevision.status.notin_(["INCORPORATED", "WITHDRAWN", "EXPIRED"]),
        )
        .all()
    )
    for row in trs:
        manual = manuals.get(row.manual_id)
        if not manual or not row.expiry_date:
            continue
        owner = _profile_owner(db, amo_id=tenant.amo_id, manual_id=row.manual_id)
        due = _as_due_datetime(row.expiry_date, zone)
        phrase = _due_phrase(due_date=row.expiry_date, today=today)
        candidates.append(_candidate(
            obligation_type="TEMPORARY_REVISION_EXPIRY",
            obligation_id=row.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=owner,
            due_at=due,
            title=f"Temporary revision expiry · {row.tr_number}",
            body=f"Temporary revision {row.tr_number} for {manual.code} is {phrase}. Incorporate, withdraw or otherwise resolve it through the governed TR lifecycle.",
            action_suffix=f"/library/{manual.id}?tab=changes",
        ))

    sources = (
        db.query(dm.ExternalDocumentSource)
        .filter(
            dm.ExternalDocumentSource.tenant_id == tenant.amo_id,
            dm.ExternalDocumentSource.status == "ACTIVE",
            dm.ExternalDocumentSource.next_check_due_at.isnot(None),
        )
        .all()
    )
    for row in sources:
        manual = manuals.get(row.manual_id)
        if not manual or not row.next_check_due_at:
            continue
        owner = _profile_owner(db, amo_id=tenant.amo_id, manual_id=row.manual_id)
        due = _as_due_datetime(row.next_check_due_at, zone)
        phrase = _due_phrase(due_date=due.astimezone(zone).date(), today=today)
        candidates.append(_candidate(
            obligation_type="EXTERNAL_SOURCE_CURRENCY",
            obligation_id=row.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=owner,
            due_at=due,
            title=f"External technical data currency · {manual.code}",
            body=f"Currency verification for {row.provider} / {manual.code} is {phrase}.",
            action_suffix="/compliance?view=external-sources",
        ))

    copies = (
        db.query(dm.DocumentControlledCopy)
        .filter(
            dm.DocumentControlledCopy.tenant_id == tenant.amo_id,
            dm.DocumentControlledCopy.status.in_(["ISSUED", "RECALLED"]),
            dm.DocumentControlledCopy.due_back_at.isnot(None),
            dm.DocumentControlledCopy.holder_user_id.isnot(None),
        )
        .all()
    )
    for row in copies:
        manual = manuals.get(row.manual_id)
        if not manual or not row.due_back_at:
            continue
        due = _as_due_datetime(row.due_back_at, zone)
        phrase = _due_phrase(due_date=due.astimezone(zone).date(), today=today)
        candidates.append(_candidate(
            obligation_type="CONTROLLED_COPY_RETURN",
            obligation_id=row.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=row.holder_user_id,
            due_at=due,
            title=f"Controlled copy return · {manual.code} / {row.copy_number}",
            body=f"Controlled copy {row.copy_number} of {manual.code} is {phrase} for return/recall control.",
            action_suffix="/distribution?view=physical-copies",
        ))

    authority_rows = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            dm.DocumentAuthoritySubmission.status.in_(["SUBMITTED", "IN_REVIEW", "QUERY_RECEIVED"]),
            dm.DocumentAuthoritySubmission.response_due_at.isnot(None),
        )
        .all()
    )
    for row in authority_rows:
        manual = manuals.get(row.manual_id)
        if not manual or not row.response_due_at:
            continue
        recipient = row.submitted_by_user_id or _profile_owner(db, amo_id=tenant.amo_id, manual_id=row.manual_id)
        due = _as_due_datetime(row.response_due_at, zone)
        phrase = _due_phrase(due_date=due.astimezone(zone).date(), today=today)
        candidates.append(_candidate(
            obligation_type="AUTHORITY_RESPONSE",
            obligation_id=row.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=recipient,
            due_at=due,
            title=f"Authority response due · {manual.code}",
            body=f"Authority submission {row.submission_reference} for {manual.code} has a response due {phrase}.",
            action_suffix=f"/library/{manual.id}?tab=workflow",
        ))

    recipient_rows = (
        db.query(dm.DocumentDistributionRecipient, dm.DocumentDistributionCampaign)
        .join(dm.DocumentDistributionCampaign, dm.DocumentDistributionCampaign.id == dm.DocumentDistributionRecipient.campaign_id)
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
            dm.DocumentDistributionRecipient.status == "PENDING",
            dm.DocumentDistributionRecipient.due_at.isnot(None),
            dm.DocumentDistributionRecipient.recipient_user_id.isnot(None),
        )
        .all()
    )
    for recipient, campaign in recipient_rows:
        manual = manuals.get(campaign.manual_id)
        if not manual or not recipient.due_at:
            continue
        due = _as_due_datetime(recipient.due_at, zone)
        phrase = _due_phrase(due_date=due.astimezone(zone).date(), today=today)
        candidates.append(_candidate(
            obligation_type="DISTRIBUTION_ACKNOWLEDGEMENT",
            obligation_id=recipient.id,
            manual=manual,
            tenant=tenant,
            recipient_user_id=recipient.recipient_user_id,
            due_at=due,
            title=f"Document acknowledgement due · {manual.code}",
            body=f"Acknowledgement for {campaign.title} / {manual.code} is {phrase}.",
            action_suffix=f"/library/{manual.id}?tab=distribution",
        ))

    return candidates


def _deliver_candidate(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    amo: account_models.AMO,
    candidate: ReminderCandidate,
    policy: DocumentReminderPolicy,
    now: datetime,
) -> int:
    zone = _local_zone(amo)
    today = now.astimezone(zone).date()
    due_date = candidate.due_at.astimezone(zone).date()
    stage = reminder_stage(due_date=due_date, today=today, policy=policy)
    if not stage:
        return 0
    primary = _active_user(db, amo_id=tenant.amo_id, user_id=candidate.recipient_user_id)
    delivered = 0
    if primary and _deliver(
        db,
        amo_id=tenant.amo_id,
        user=primary,
        candidate=candidate,
        stage=stage,
        title=candidate.title,
        body=candidate.body,
        policy=policy,
        now=now,
    ):
        delivered += 1

    overdue_days = _days_overdue(due_date=due_date, today=today)
    if overdue_days < policy.owner_escalation_days:
        return delivered

    owner_id = _profile_owner(db, amo_id=tenant.amo_id, manual_id=candidate.manual_id)
    owner = _active_user(db, amo_id=tenant.amo_id, user_id=owner_id)
    bucket = ((overdue_days - 1) // policy.overdue_repeat_days) + 1
    if owner and (not primary or str(owner.id) != str(primary.id)):
        if _deliver(
            db,
            amo_id=tenant.amo_id,
            user=owner,
            candidate=candidate,
            stage=f"OWNER_ESCALATION_W{bucket}",
            title=f"Overdue Document Control escalation · {candidate.title}",
            body=f"{candidate.body} This overdue obligation has been escalated to the governed document owner.",
            policy=policy,
            now=now,
        ):
            delivered += 1

    if overdue_days < policy.quality_escalation_days:
        return delivered
    quality_id = _quality_escalation_user(db, amo_id=tenant.amo_id)
    quality = _active_user(db, amo_id=tenant.amo_id, user_id=quality_id)
    if quality and (not primary or str(quality.id) != str(primary.id)) and (not owner or str(quality.id) != str(owner.id)):
        if _deliver(
            db,
            amo_id=tenant.amo_id,
            user=quality,
            candidate=candidate,
            stage=f"QUALITY_ESCALATION_W{bucket}",
            title=f"Quality escalation · {candidate.title}",
            body=f"{candidate.body} This Document Control obligation remains overdue beyond the configured Quality escalation threshold.",
            policy=policy,
            now=now,
        ):
            delivered += 1
    return delivered


def run_document_control_reminder_cycle(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        acquired = bool(db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}).scalar())
        if not acquired:
            return {"tenants": 0, "candidates": 0, "deliveries": 0, "lock_skipped": 1}

    tenants = db.query(manual_models.Tenant).order_by(manual_models.Tenant.slug.asc()).all()
    candidate_count = 0
    delivery_count = 0
    enabled_tenants = 0
    for tenant in tenants:
        policy = reminder_policy_from_settings(dict(tenant.settings_json or {}))
        if not policy.enabled:
            continue
        amo = db.query(account_models.AMO).filter(account_models.AMO.id == tenant.amo_id, account_models.AMO.is_active.is_(True)).first()
        if not amo:
            continue
        enabled_tenants += 1
        candidates = _collect_candidates(db, tenant=tenant, amo=amo, now=now)
        candidate_count += len(candidates)
        for candidate in candidates:
            delivery_count += _deliver_candidate(
                db,
                tenant=tenant,
                amo=amo,
                candidate=candidate,
                policy=policy,
                now=now,
            )
    db.commit()
    return {
        "tenants": enabled_tenants,
        "candidates": candidate_count,
        "deliveries": delivery_count,
        "lock_skipped": 0,
    }


def _scheduler_loop() -> None:
    while not _stop_event.is_set():
        db = WriteSessionLocal()
        try:
            result = run_document_control_reminder_cycle(db)
            logger.info("Document Control reminder cycle completed: %s", result)
        except Exception:
            db.rollback()
            logger.exception("Document Control automatic reminder cycle failed")
        finally:
            close_session_safely(db)
        _stop_event.wait(REMINDER_INTERVAL_SECONDS)


def start_document_control_reminder_scheduler() -> None:
    global _thread
    with _thread_lock:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_scheduler_loop, name="document-control-reminders", daemon=True)
        _thread.start()


def stop_document_control_reminder_scheduler() -> None:
    global _thread
    _stop_event.set()
    thread = _thread
    if thread and thread.is_alive():
        thread.join(timeout=5)
    _thread = None
