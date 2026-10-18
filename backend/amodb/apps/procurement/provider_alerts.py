"""Phase 8 provider reminders through the existing tenant notification services.

The ledger records work to dispatch; QMSNotification, partner notifications and
notifications.service remain the only user-facing delivery systems.
Domain decisions, supplier eligibility and maintenance permissions never depend
on this best-effort worker.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError

from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models as quality
from amodb.apps.quality.tenant_security import set_postgres_tenant_context
from amodb.apps.notifications import service as mail_service
from amodb.database import SessionLocal

LOGGER = logging.getLogger(__name__)
DEFAULT_LEADS = [120, 90, 60, 30, 14, 7]
DEPARTMENTS = ("QUALITY", "PROCUREMENT", "MAINTENANCE", "STORES")
DEFAULT_ROUTES = {
    "QUALITY": ["QUALITY_MANAGER", "QUALITY_OFFICER"],
    "PROCUREMENT": ["PROCUREMENT_MANAGER", "PROCUREMENT_OFFICER"],
    "MAINTENANCE": ["BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER", "WORKSHOP_MANAGER"],
    "STORES": ["STORES_MANAGER", "STOREKEEPER"],
}
# Catalog is a controlled vocabulary, not evidence that every source currently
# exposes every event. Existing QMS Audit/CAR notifications retain their ownership.
CATALOG = {
    "provider.registration": "QUALITY",
    "provider.approval_requested": "QUALITY",
    "provider.missing_evidence": "QUALITY",
    "provider.technical_review_pending": "MAINTENANCE",
    "provider.quality_review_pending": "QUALITY",
    "provider.approved": "QUALITY",
    "provider.rejected": "QUALITY",
    "provider.scope_restricted": "QUALITY",
    "provider.suspended": "QUALITY",
    "provider.reinstated": "QUALITY",
    "provider.approval_expiry": "QUALITY",
    "provider.certificate_expiry": "QUALITY",
    "provider.site_capability_change": "QUALITY",
    "contract.review_pending": "QUALITY",
    "contract.ack_pending": "QUALITY",
    "contract.expiry": "QUALITY",
    "contract.renewal_notice": "QUALITY",
    "contract.suspended_terminated": "QUALITY",
    "contract.replacement_missing": "QUALITY",
    "quality.audit_due": "QUALITY",
    "quality.audit_notice": "QUALITY",
    "quality.audit_rescheduled": "QUALITY",
    "quality.ack_overdue": "QUALITY",
    "quality.document_requested": "QUALITY",
    "quality.evidence_received": "QUALITY",
    "quality.evidence_rejected": "QUALITY",
    "quality.finding_issued": "QUALITY",
    "quality.car_due": "QUALITY",
    "quality.capa_overdue": "QUALITY",
    "quality.effectiveness_due": "QUALITY",
    "quality.repeat_finding": "QUALITY",
    "procurement.rfq_invited": "PROCUREMENT",
    "procurement.clarification": "PROCUREMENT",
    "procurement.quote_due": "PROCUREMENT",
    "procurement.quote_received": "PROCUREMENT",
    "procurement.po_issued": "PROCUREMENT",
    "procurement.po_ack_due": "PROCUREMENT",
    "procurement.delivery_changed": "PROCUREMENT",
    "procurement.shipment_submitted": "PROCUREMENT",
    "procurement.material_received": "STORES",
    "procurement.inspection_discrepancy": "STORES",
    "procurement.quality_hold": "QUALITY",
    "procurement.return_rma": "PROCUREMENT",
    "maintenance.assigned": "MAINTENANCE",
    "maintenance.ack_overdue": "MAINTENANCE",
    "maintenance.additional_pending": "MAINTENANCE",
    "maintenance.progress_overdue": "MAINTENANCE",
    "maintenance.completion_missed": "MAINTENANCE",
    "maintenance.release_submitted": "MAINTENANCE",
    "maintenance.release_missing": "MAINTENANCE",
    "maintenance.inspection_pending": "STORES",
    "maintenance.closure_pending": "MAINTENANCE",
}

MAINTENANCE_ACTIONS = {
    "DISPATCH": "maintenance.assigned",
    "PROVIDER_ACCEPT": "maintenance.assigned",
    "ADDITIONAL_REQUEST": "maintenance.additional_pending",
    "SUBMIT_RELEASE": "maintenance.release_submitted",
    "RETURN": "maintenance.inspection_pending",
    "RECEIVE": "maintenance.closure_pending",
    "TECHNICAL_ACCEPT": "maintenance.closure_pending",
}
PROCUREMENT_ACTIONS = {
    "RFQ_INVITED": "procurement.rfq_invited",
    "CLARIFICATION": "procurement.clarification",
    "QUOTE_SUBMITTED": "procurement.quote_received",
    "SUBMIT_QUOTE": "procurement.quote_received",
    "PO_ISSUED": "procurement.po_issued",
    "ACK_PO": "procurement.po_ack_due",
    "SHIPMENT_SUBMITTED": "procurement.shipment_submitted",
    "SHIPMENT_ADVISED": "procurement.shipment_submitted",
    "PROPOSE_DELIVERY_DATE": "procurement.delivery_changed",
    "RETURN_REQUESTED": "procurement.return_rma",
    "INSPECTION_DISCREPANCY": "procurement.inspection_discrepancy",
    "QUALITY_HOLD": "procurement.quality_hold",
}

def defaults():
    return {
        "lead_days_json": DEFAULT_LEADS[:],
        "escalation_days_json": [0, 3, 7],
        "routes_json": {key: list(value) for key, value in DEFAULT_ROUTES.items()},
        "channels_json": {"in_app": True, "email": False},
        "templates_json": {},
        "digest_json": {"enabled": False, "hour": 8},
        "quiet_hours_json": {"enabled": False, "start": "21:00", "end": "07:00"},
    }

def _rows(db, statement, **params):
    return db.execute(text(statement), params).mappings().all()

def _policy(db, tenant):
    row = db.execute(text("SELECT * FROM external_provider_alert_policies WHERE amo_id=:amo"),
                     {"amo": tenant}).mappings().first()
    if row:
        return dict(row)
    return dict(defaults(), amo_id=tenant, revision=0)

def _utc(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time(8, 0))
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _fingerprint(tenant, source, source_id, stamp, event, recipient_kind, recipient_id, due):
    payload = json.dumps([tenant, source, str(source_id), str(stamp), event,
                          recipient_kind, str(recipient_id), due.isoformat()], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()

def _qualifying_users(db, amo, roles):
    if not roles:
        return []
    users = db.query(accounts.User).filter(accounts.User.amo_id == amo,
                                            accounts.User.is_active.is_(True)).all()
    return [u for u in users if str(getattr(u.role, "value", u.role)) in roles]

def _queue(db, *, amo, event, source, source_id, stamp, supplier=None, due=None, recipient_kind="staff",
           provider=None, recipient_id=None, cancel_older=False):
    if event not in CATALOG:
        return 0
    due = _utc(due or datetime.now(timezone.utc))
    if due is None:
        return 0
    policy = _policy(db, amo)
    dept = CATALOG[event]
    recipients = []
    if recipient_kind == "staff":
        recipients = [("staff", str(user.id), None) for user in
                      _qualifying_users(db, amo, policy["routes_json"].get(dept, []))]
    elif provider and recipient_id:
        recipients = [("provider", str(recipient_id), str(provider))]
    count = 0
    for kind, person, provider_id in recipients:
        fingerprint = _fingerprint(amo, source, source_id, stamp, event, kind, person, due)
        if cancel_older:
            db.execute(text("""UPDATE external_provider_alert_jobs
                SET status='CANCELLED', cancelled_at=NOW(), updated_at=NOW()
                WHERE amo_id=:amo AND source_kind=:kind AND source_id=:source
                AND event_key=:event AND status IN ('PENDING','RETRY')
                AND fingerprint<>:fingerprint AND
                ((recipient_user_id=:person AND :provider IS NULL)
                  OR (recipient_identity_id=:person AND recipient_provider_id=:provider))"""),
                dict(amo=amo,kind=source,source=str(source_id),event=event,
                     fingerprint=fingerprint,person=person,provider=provider_id))
        values = dict(id=str(uuid4()), amo=amo, fingerprint=fingerprint, event=event,
                      kind=source, source=str(source_id), stamp=str(stamp)[:128],
                      supplier=supplier, due=due, user=person if kind=="staff" else None,
                      identity=person if kind=="provider" else None, provider=provider_id)
        inserted = db.execute(text("""INSERT INTO external_provider_alert_jobs
           (id,amo_id,fingerprint,event_key,source_kind,source_id,source_stamp,
            supplier_id,recipient_user_id,recipient_identity_id,recipient_provider_id,due_at)
           VALUES(:id,:amo,:fingerprint,:event,:kind,:source,:stamp,
                  :supplier,:user,:identity,:provider,:due)
           ON CONFLICT (amo_id,fingerprint) DO NOTHING"""), values)
        count += inserted.rowcount
    return count

def _local_day(instant, zone):
    return instant.astimezone(zone).date()

def _schedule_expiries(db, amo, local_now, zone, policy):
    count = 0
    sources = [
        ("certificate", "provider.certificate_expiry", """SELECT id,supplier_id,valid_until AS due
             FROM external_provider_certificates WHERE amo_id=:amo
             AND verification_state='VERIFIED' AND valid_until IS NOT NULL"""),
        ("capability", "provider.approval_expiry", """SELECT id,supplier_id,valid_until AS due
             FROM external_provider_capabilities WHERE amo_id=:amo AND valid_until IS NOT NULL"""),
        ("evidence", "provider.approval_expiry", """SELECT id,supplier_id,valid_until AS due
             FROM quality_external_provider_evidence WHERE amo_id=:amo
             AND status='VERIFIED' AND valid_until IS NOT NULL"""),
        ("agreement", "contract.expiry", """SELECT id,supplier_id,expires_on AS due
             FROM quality_external_provider_contracts WHERE amo_id=:amo
             AND status='ACTIVE' AND expires_on IS NOT NULL"""),
        ("qualification", "provider.approval_expiry", """SELECT id,supplier_id,next_review_due_on AS due
             FROM quality_provider_qualification_cases WHERE amo_id=:amo
             AND status IN ('APPROVED','CONDITIONALLY_APPROVED')
             AND next_review_due_on IS NOT NULL AND NOT EXISTS
             (SELECT 1 FROM quality_provider_qualification_cases newer
                WHERE newer.amo_id=quality_provider_qualification_cases.amo_id
                AND newer.supplier_id=quality_provider_qualification_cases.supplier_id
                AND newer.created_at>quality_provider_qualification_cases.created_at
                AND newer.status IN ('APPROVED','CONDITIONALLY_APPROVED'))"""),
    ]
    for source, event, query in sources:
        for row in _rows(db, query, amo=amo):
            target = row["due"]
            if not target:
                continue
            if isinstance(target, datetime):
                due_date = _local_day(_utc(target), zone)
            else:
                due_date = target
            for lead in policy["lead_days_json"]:
                remind_date = due_date - timedelta(days=lead)
                # Scan lookahead is the upcoming day, not all history; first
                # deployment deliberately schedules expired obligations as overdue.
                if remind_date > _local_day(local_now, zone) + timedelta(days=1):
                    continue
                remind_at = datetime.combine(remind_date, time(8, 0), zone).astimezone(timezone.utc)
                count += _queue(db, amo=amo, event=event, source=source, source_id=row["id"],
                                stamp=str(due_date)+":"+str(lead), supplier=row["supplier_id"],
                                due=remind_at, cancel_older=True)
    return count

def _scan_transitions(db, amo):
    count = 0
    for row in _rows(db, """SELECT e.id,e.action,e.work_id AS entity_id,
                    w.supplier_id FROM external_contracted_work_events e
                    JOIN external_contracted_work w ON w.id=e.work_id AND w.amo_id=e.amo_id
                    WHERE e.amo_id=:amo ORDER BY e.created_at DESC LIMIT 500""", amo=amo):
        event = MAINTENANCE_ACTIONS.get(row["action"])
        if event:
            count += _queue(db, amo=amo,event=event,source="maintenance_event",
                            source_id=row["entity_id"],stamp=row["id"],supplier=row["supplier_id"])
    for row in _rows(db, """SELECT id,entity_type,entity_id,action,supplier_id
                   FROM external_procurement_events WHERE amo_id=:amo
                   ORDER BY created_at DESC LIMIT 500""", amo=amo):
        event = PROCUREMENT_ACTIONS.get(row["action"])
        if event:
            count += _queue(db, amo=amo,event=event,source="procurement_event",
                            source_id=row["entity_id"],stamp=row["id"],supplier=row["supplier_id"])
    for row in _rows(db, """SELECT id,supplier_id,status,version,technical_state
        FROM quality_provider_qualification_cases WHERE amo_id=:amo
        AND status IN ('SUBMITTED','IN_REVIEW','READY','APPROVED','CONDITIONALLY_APPROVED','REJECTED')
        ORDER BY updated_at DESC LIMIT 200""", amo=amo):
        event = ("provider.approved" if row["status"] in ("APPROVED","CONDITIONALLY_APPROVED")
                 else "provider.rejected" if row["status"]=="REJECTED"
                 else "provider.technical_review_pending" if row["technical_state"]=="PENDING"
                 else "provider.quality_review_pending")
        count += _queue(db,amo=amo,event=event,source="qualification",source_id=row["id"],
                        stamp=str(row["version"])+":"+row["status"],supplier=row["supplier_id"],
                        cancel_older=True)
    return count

def _allowed_link(amo_code, row):
    from urllib.parse import quote
    code = quote(str(amo_code), safe="")
    source = row["source_kind"]
    supplier = row["supplier_id"]
    if source in ("certificate","capability","evidence","qualification","agreement") and supplier:
        tab = "contracts" if source=="agreement" else "qualification" if source=="qualification" else "evidence"
        return "/maintenance/"+code+"/quality/suppliers/"+str(int(supplier))+"/"+tab
    if source == "maintenance_event":
        return "/maintenance/"+code+"/contracted-work"
    if source == "procurement_event":
        return "/maintenance/"+code+"/procurement"
    return "/maintenance/"+code+"/quality/suppliers"

def _restricted_now(local, quiet):
    if not quiet.get("enabled"):
        return False
    try:
        start = time.fromisoformat(quiet["start"])
        end = time.fromisoformat(quiet["end"])
    except (ValueError, KeyError, TypeError):
        return False
    clock = local.time().replace(tzinfo=None)
    return start <= clock < end if start < end else clock >= start or clock < end

def _dispatch(db, amo, code, zone, policy, now):
    delivered = 0
    jobs = _rows(db, """SELECT * FROM external_provider_alert_jobs WHERE amo_id=:amo
       AND status IN ('PENDING','RETRY') AND due_at<=:now
       AND (next_attempt_at IS NULL OR next_attempt_at<=:now)
       ORDER BY due_at,id LIMIT 100 FOR UPDATE SKIP LOCKED""", amo=amo,now=now)
    for job in jobs:
        try:
            recipient = None
            if job["recipient_user_id"]:
                recipient = db.query(accounts.User).filter(
                    accounts.User.amo_id==amo,
                    accounts.User.id==job["recipient_user_id"],
                    accounts.User.is_active.is_(True)).first()
                if recipient is None:
                    db.execute(text("""UPDATE external_provider_alert_jobs
                         SET status='CANCELLED',cancelled_at=NOW() WHERE id=:id"""), {"id":job["id"]})
                    continue
            elif job["recipient_identity_id"]:
                # Never deliver to revoked identities or grants. A vendor may
                # only receive a scoped record; no generic supplier-wide broadcast.
                grant = _rows(db, """SELECT g.object_scope_json FROM external_tenant_grants g
                   JOIN external_organization_memberships m ON m.id=g.membership_id
                   JOIN external_identities i ON i.id=m.identity_id
                   WHERE g.amo_id=:amo AND g.tenant_provider_id=:provider
                   AND i.id=:identity AND g.status='ACTIVE' AND m.status='ACTIVE'
                   AND i.status='ACTIVE'""", amo=amo,provider=job["recipient_provider_id"],
                   identity=job["recipient_identity_id"])
                scope_kind = "contracted_work" if job["source_kind"]=="maintenance_event" else "procurement"
                if not any(str(job["source_id"]) in [str(v) for v in
                    (g["object_scope_json"] or {}).get(scope_kind, [])] for g in grant):
                    db.execute(text("""UPDATE external_provider_alert_jobs
                         SET status='CANCELLED',cancelled_at=NOW() WHERE id=:id"""), {"id":job["id"]})
                    continue
            else:
                continue
            # Sensitive descriptions, evidence names, internal notes and
            # object-store URLs are deliberately absent from notification text.
            message = "External provider action: " + job["event_key"].replace(".", " / ").replace("_", " ")
            label = "Review assigned provider record"
            if not job["in_app_id"] and policy["channels_json"].get("in_app", True):
                if recipient:
                    notice = quality.QMSNotification(
                        amo_id=amo, user_id=str(recipient.id), message=message,
                        severity=quality.QMSNotificationSeverity.ACTION_REQUIRED,
                        entity_type="provider_alert", entity_id=job["id"],
                        action_url=_allowed_link(code, job), action_label=label)
                    db.add(notice)
                    db.flush()
                    new_id = str(notice.id)
                else:
                    new_id = str(uuid4())
                    db.execute(text("""INSERT INTO external_partner_notifications
                     (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
                     VALUES(:id,:amo,:provider,:identity,'ACTION','Provider action',
                         :message,'PROVIDER_ALERT',:resource)"""),
                         dict(id=new_id,amo=amo,provider=job["recipient_provider_id"],
                              identity=job["recipient_identity_id"],message=message,
                              resource=str(job["id"])))
                db.execute(text("""UPDATE external_provider_alert_jobs
                   SET in_app_id=:notification,updated_at=NOW() WHERE id=:id"""),
                   {"notification":new_id,"id":job["id"]})
            # A Resend API acknowledgement is NOT email delivery, inbox placement
            # or a read receipt. That evidence belongs to the signed webhook log.
            email_on = policy["channels_json"].get("email",False) and recipient is not None
            if email_on and not job["email_log_id"]:
                local = now.astimezone(zone)
                digest = policy["digest_json"]
                blocked = (_restricted_now(local,policy["quiet_hours_json"])
                           or (digest.get("enabled") and local.hour != digest.get("hour",8)))
                if blocked:
                    retry = now+timedelta(hours=1)
                    db.execute(text("""UPDATE external_provider_alert_jobs SET
                        status='RETRY',next_attempt_at=:retry,updated_at=NOW()
                        WHERE id=:id"""),{"retry":retry,"id":job["id"]})
                    continue
                email = mail_service.send_email("provider.lifecycle",getattr(recipient,"email",None),
                    "External provider action requires review",
                    {"summary":message, "url":_allowed_link(code,job)},job["fingerprint"],
                    amo_id=amo,db=db,recipient_user_id=str(recipient.id),
                    audit_context={"event_key":job["event_key"],"job_id":job["id"]})
                db.execute(text("""UPDATE external_provider_alert_jobs
                   SET email_log_id=:log WHERE id=:id"""),{"log":str(email.id),"id":job["id"]})
            db.execute(text("""UPDATE external_provider_alert_jobs SET status='DELIVERED',
                  delivered_at=NOW(),next_attempt_at=NULL,last_error=NULL,updated_at=NOW()
                  WHERE id=:id"""),{"id":job["id"]})
            delivered += 1
        except Exception as exc:
            # Roll back only the failing recipient. Do not erase other notices.
            LOGGER.exception("Provider alert dispatch failed %s",job["id"])
            attempts = int(job["attempts"])+1
            db.execute(text("""UPDATE external_provider_alert_jobs
                 SET status=:status,attempts=:attempts,last_error=:error,
                     next_attempt_at=:next,updated_at=NOW() WHERE id=:id"""),
                dict(id=job["id"], status="FAILED" if attempts>=8 else "RETRY",
                     attempts=attempts,error=type(exc).__name__[:500],
                     next=now+timedelta(minutes=min(1440,2**min(attempts,10)))))
    return delivered

def scan_provider_alerts():
    """Existing scheduled process calls this every hour; tenant failures isolate."""
    now = datetime.now(timezone.utc)
    report = {"tenants":0, "enqueued":0, "dispatched":0, "failed_tenants":0}
    with SessionLocal() as db:
        if not inspect(db.get_bind()).has_table("external_provider_alert_jobs"):
            return report
        tenants = db.query(accounts.AMO.id,accounts.AMO.amo_code,
                           accounts.AMO.time_zone).filter(accounts.AMO.is_active.is_(True)).all()
        db.rollback()
        for amo, code, tzname in tenants:
            try:
                set_postgres_tenant_context(db,amo_id=str(amo),user_id="")
                if db.get_bind().dialect.name=="postgresql":
                    db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
                try:
                    zone = ZoneInfo(tzname or "UTC")
                except ZoneInfoNotFoundError:
                    zone = ZoneInfo("UTC")
                policy = _policy(db, str(amo))
                report["enqueued"] += _scan_transitions(db,str(amo))
                report["enqueued"] += _schedule_expiries(db,str(amo),now,zone,policy)
                report["dispatched"] += _dispatch(db,str(amo),code,zone,policy,now)
                db.commit()
                report["tenants"] += 1
            except Exception:
                db.rollback()
                report["failed_tenants"] += 1
                LOGGER.exception("Phase 8 provider alert tenant scan failed %s",amo)
    return report
