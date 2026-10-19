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
    "provider.overdue_escalation": "QUALITY",
    "provider.documentation_updated": "QUALITY",
    "provider.review_updated": "QUALITY",
    "provider.reinstated": "QUALITY",
    "provider.approval_expiry": "QUALITY",
    "provider.certificate_expiry": "QUALITY",
    "provider.site_capability_change": "QUALITY",
    "provider.site_capability_proposed": "QUALITY",
    "contract.review_pending": "QUALITY",
    "contract.ack_pending": "QUALITY",
    "contract.acknowledged": "QUALITY",
    "contract.clarification_requested": "QUALITY",
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
    "quality.evidence_reviewed": "QUALITY",
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
    "procurement.po_acknowledged": "PROCUREMENT",
    "procurement.delivery_due": "PROCUREMENT",
    "procurement.delivery_changed": "PROCUREMENT",
    "procurement.shipment_submitted": "PROCUREMENT",
    "procurement.material_received": "STORES",
    "procurement.inspection_discrepancy": "STORES",
    "procurement.quality_hold": "QUALITY",
    "procurement.quality_released": "QUALITY",
    "procurement.inspection_completed": "STORES",
    "procurement.return_rma": "PROCUREMENT",
    "maintenance.assigned": "MAINTENANCE",
    "maintenance.acknowledged": "MAINTENANCE",
    "maintenance.progress_updated": "MAINTENANCE",
    "maintenance.finding_reported": "MAINTENANCE",
    "maintenance.date_change_requested": "MAINTENANCE",
    "maintenance.schedule_changed": "MAINTENANCE",
    "maintenance.rework_notice": "MAINTENANCE",
    "maintenance.hold_notice": "MAINTENANCE",
    "maintenance.resumed_notice": "MAINTENANCE",
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
    "PROVIDER_ACCEPT": "maintenance.acknowledged",
    "ADDITIONAL_WORK_REQUESTED": "maintenance.additional_pending",
    "EXPECTED_DATES_CHANGED": "maintenance.schedule_changed",
    "PROGRESS": "maintenance.progress_updated",
    "ETA_CHANGE": "maintenance.date_change_requested",
    "FINDING": "maintenance.finding_reported",
    "SUBMIT_RELEASE": "maintenance.release_submitted",
    "RETURN": "maintenance.inspection_pending",
    "RECEIVE": "maintenance.closure_pending",
    "TECHNICAL_ACCEPT": "maintenance.closure_pending",
}
PROCUREMENT_ACTIONS = {
    "RFQ_INVITED": "procurement.rfq_invited",
    "CLARIFICATION": "procurement.clarification",
    "QUOTE_RECEIVED": "procurement.quote_received",
    "SUBMITTED": "procurement.quote_received",
    # Canonical ProcurementPurchaseOrder/send already covers this same PO
    # transition; do not also project the partner PO_ISSUED mirror.
    "ACKNOWLEDGED": "procurement.po_acknowledged",
    "SHIPMENT_SUBMITTED": "procurement.shipment_submitted",
    "SHIPMENT_ADVISED": "procurement.shipment_submitted",
    "DELIVERY_CHANGE": "procurement.delivery_changed",
    "RETURN": "procurement.return_rma",
    "RMA": "procurement.return_rma",
    "REJECTED_MATERIAL": "procurement.inspection_discrepancy",
    "QUALITY_HOLD": "procurement.quality_hold",
}

def defaults():
    return {
        "lead_days_json": {name: DEFAULT_LEADS[:] for name in DEPARTMENTS},
        "escalation_days_json": {name: [0, 3, 7] for name in DEPARTMENTS},
        "routes_json": {key: list(value) for key, value in DEFAULT_ROUTES.items()},
        "channels_json": {name: {"in_app": True, "email": False} for name in DEPARTMENTS},
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
                          recipient_kind, str(recipient_id)], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()

def _qualifying_users(db, amo, roles):
    if not roles:
        return []
    # Keep role filtering within the indexed tenant query. Do not load every
    # user into the hourly scheduler for each notification event.
    return db.query(accounts.User).filter(
        accounts.User.amo_id == amo, accounts.User.is_active.is_(True),
        accounts.User.role.in_(roles)).all()

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

# Only trusted, explicitly enumerated source tables may drive expiry events.
# Event-source checks run again at dispatch to cancel superseded reminders.
DATE_SOURCES = {
    "certificate": ("external_provider_certificates", "valid_until", "verification_state='VERIFIED'"),
    "capability": ("external_provider_capabilities", "valid_until", "1=1"),
    "evidence": ("quality_external_provider_evidence", "valid_until", "status='VERIFIED'"),
    "agreement": ("quality_external_provider_contracts", "expires_on", "status='ACTIVE'"),
    "qualification": ("quality_provider_qualification_cases", "next_review_due_on",
                      "status IN ('APPROVED','CONDITIONALLY_APPROVED')"),
    "surveillance": ("quality_provider_surveillance", "due_on", "outcome IN ('SCHEDULED','IN_PROGRESS')"),
    "rfq": ("procurement_rfqs", "response_due_at", "status IN ('ISSUED','PARTIALLY_RESPONDED') AND EXISTS ("
            "SELECT 1 FROM procurement_rfq_suppliers invited WHERE invited.rfq_id=procurement_rfqs.id "
            "AND invited.responded_at IS NULL AND invited.declined_at IS NULL)"),
    "po_delivery": ("procurement_purchase_orders", "promised_delivery_date",
                    "status NOT IN ('CANCELLED','CLOSED','FULFILLED')"),
}
SOURCE_EVENT = {
    "certificate": "provider.certificate_expiry",
    "capability": "provider.approval_expiry",
    "evidence": "provider.approval_expiry",
    "agreement": "contract.expiry",
    "qualification": "provider.approval_expiry",
    "surveillance": "quality.audit_due",
    "rfq": "procurement.quote_due",
    "po_delivery": "procurement.delivery_due",
}

def _active_source(db, tenant, source, source_id):
    if source not in DATE_SOURCES:
        return None
    table, column, predicate = DATE_SOURCES[source]
    base_id = str(source_id).split(":")[0]
    # The table and column are constants in this module, never request values.
    query = f"SELECT id, {column} AS due FROM {table} WHERE amo_id=:amo AND id=:id AND {predicate}"
    row = db.execute(text(query), {"amo": tenant, "id": base_id}).mappings().first()
    if source == "qualification" and row:
        newer = db.execute(text("""SELECT 1 FROM quality_provider_qualification_cases newer
            JOIN quality_provider_qualification_cases old
            ON old.amo_id=newer.amo_id AND old.supplier_id=newer.supplier_id
            WHERE old.amo_id=:amo AND old.id=:id
            AND newer.created_at>old.created_at
            AND newer.status IN ('APPROVED','CONDITIONALLY_APPROVED')
            LIMIT 1"""), {"amo":tenant,"id":base_id}).first()
        if newer:
            return None
    return row

def _date_in_tenant_zone(target, zone):
    if isinstance(target, date) and not isinstance(target, datetime):
        return target
    value = _utc(target)
    return value.astimezone(zone).date() if value else None

def _schedule_expiries(db, amo, local_now, zone, policy):
    count = 0
    today = _local_day(local_now,zone)
    for source, (table, column, predicate) in DATE_SOURCES.items():
        event = SOURCE_EVENT[source]
        if source == "rfq":
            query = f"""SELECT id,NULL AS supplier_id,{column} AS due FROM {table}
               WHERE amo_id=:amo AND {predicate} AND {column} IS NOT NULL"""
        else:
            query = f"""SELECT id,supplier_id,{column} AS due FROM {table}
               WHERE amo_id=:amo AND {predicate} AND {column} IS NOT NULL"""
        # Tenant policy permits up to 365-day leads/escalations. Never sweep
        # all historic certificates/agreements every scheduler invocation.
        query += f" AND {column}>=:window_start AND {column}<:window_end"
        for row in _rows(db, query, amo=amo,
                         window_start=today-timedelta(days=366),
                         window_end=today+timedelta(days=367)):
            due_date = _date_in_tenant_zone(row["due"], zone)
            if due_date is None:
                continue
            if source == "qualification" and _active_source(db,amo,source,row["id"]) is None:
                continue
            department = CATALOG[event]
            leads = [(lead,"lead",due_date-timedelta(days=lead))
                     for lead in policy["lead_days_json"].get(department, DEFAULT_LEADS)]
            overdue = [(lag,"overdue",due_date+timedelta(days=lag))
                       for lag in policy["escalation_days_json"].get(department,[])
                       if lag>=0]
            for offset, kind, remind_date in leads+overdue:
                # Backfill is bounded to the present local day: never flood a
                # newly onboarded tenant with years of historical reminders.
                if remind_date<today-timedelta(days=7) or remind_date>today+timedelta(days=1):
                    continue
                remind_at = datetime.combine(remind_date,time(8,0),zone).astimezone(timezone.utc)
                # Distinct milestone identities avoid cancelling a 90-day alert
                # when a later 60-day alert is inserted.
                suffix = f"{kind}:{offset}"
                count += _queue(db,amo=amo,event=event,source=source,
                                source_id=f"{row['id']}:{suffix}",
                                stamp=f"{due_date}:{suffix}",supplier=row.get("supplier_id"),
                                due=remind_at,cancel_older=True)
            if source == "agreement":
                notice = db.execute(text("""SELECT termination_notice_days FROM
                    quality_external_provider_contracts WHERE amo_id=:amo AND id=:id"""),
                    {"amo":amo,"id":row["id"]}).scalar()
                if notice is not None and 0<=int(notice)<=365:
                    remind = due_date-timedelta(days=int(notice))
                    if today<=remind<=today+timedelta(days=1):
                        count += _queue(db,amo=amo,event="contract.renewal_notice",source=source,
                            source_id=f"{row['id']}:notice",stamp=f"{due_date}:notice:{notice}",
                            supplier=row["supplier_id"],
                            due=datetime.combine(remind,time(8,0),zone).astimezone(timezone.utc),
                            cancel_older=True)
    # Purchase order acknowledgements are tracked against canonical supplier
    # acknowledgement, never against manually-entered frontend badge states.
    for row in _rows(db, """SELECT id,supplier_id,sent_at FROM procurement_purchase_orders
       WHERE amo_id=:amo AND sent_at IS NOT NULL AND supplier_ack_reference IS NULL AND acknowledged_at IS NULL
         AND status NOT IN ('CANCELLED','CLOSED','ACKNOWLEDGED','FULFILLED') ORDER BY sent_at DESC LIMIT 200""",amo=amo):
        sent = _utc(row["sent_at"])
        if sent and _local_day(sent,zone)<=today:
            count += _queue(db,amo=amo,event="procurement.po_ack_due",source="po_ack",
                            source_id=str(row["id"]),stamp=str(sent.date()),
                            supplier=row["supplier_id"],due=sent,cancel_older=True)
    return count

def _scan_transitions(db, amo):
    """Read immutable, authority-owned source transitions; not frontend state."""
    count = 0
    for row in _rows(db, """SELECT e.id,e.action,e.work_id AS entity_id,
                    w.supplier_id FROM external_contracted_work_events e
                    JOIN external_contracted_work w ON w.id=e.work_id AND w.amo_id=e.amo_id
                    WHERE e.amo_id=:amo ORDER BY e.created_at DESC LIMIT 500""", amo=amo):
        event=MAINTENANCE_ACTIONS.get(row["action"])
        if event:
            count+=_queue(db,amo=amo,event=event,source="maintenance_event",
                          source_id=row["entity_id"],stamp=row["id"],supplier=row["supplier_id"])
    # Phase 7 already delegates work identity by individual object grants.
    # Only a member assigned THIS exact work receives the vendor projection.
    for row in _rows(db, """SELECT e.id,e.action,e.work_id AS entity_id,w.supplier_id,w.provider_id
        FROM external_contracted_work_events e
        JOIN external_contracted_work w ON w.amo_id=e.amo_id AND w.id=e.work_id
        WHERE e.amo_id=:amo AND e.action IN ('DISPATCH','REWORK','HOLD','RESUME')
        ORDER BY e.created_at DESC LIMIT 200""",amo=amo):
        for grant in _rows(db, """SELECT g.object_scope_json,
            m.identity_id,i.status AS identity_status
            FROM external_tenant_grants g
            JOIN external_organization_memberships m ON m.id=g.membership_id
            JOIN external_identities i ON i.id=m.identity_id
            WHERE g.amo_id=:amo AND g.tenant_provider_id=:provider
              AND g.status='ACTIVE' AND m.status='ACTIVE' AND i.status='ACTIVE'""",
              amo=amo,provider=row["provider_id"]):
            if str(row["entity_id"]) not in {str(item) for item in
                    (grant["object_scope_json"] or {}).get("contracted_work",[])}:
                continue
            vendor_event={"DISPATCH":"maintenance.assigned",
                          "REWORK":"maintenance.rework_notice",
                          "HOLD":"maintenance.hold_notice",
                          "RESUME":"maintenance.resumed_notice"}.get(row["action"])
            if not vendor_event:
                continue
            count+=_queue(db,amo=amo,
                          event=vendor_event,source="maintenance_event",
                          source_id=row["entity_id"],stamp=row["id"],
                          supplier=row["supplier_id"],recipient_kind="provider",
                          provider=row["provider_id"],recipient_id=grant["identity_id"])
    for row in _rows(db, """SELECT id,entity_type,entity_id,action,supplier_id
                   FROM external_procurement_events WHERE amo_id=:amo
                   ORDER BY created_at DESC LIMIT 500""",amo=amo):
        event=PROCUREMENT_ACTIONS.get(row["action"])
        if row["action"]=="SUBMITTED":
            continue
        if row["action"]=="ACKNOWLEDGED" and row["entity_type"]!="PO":
            continue
        if event:
            count+=_queue(db,amo=amo,event=event,source="procurement_event",
                          source_id=row["entity_id"],stamp=row["id"],supplier=row["supplier_id"])
    governance={
        "QUALIFICATION_OPENED":"provider.approval_requested",
        "QUALIFICATION_UPDATED":"provider.documentation_updated",
        "DEPARTMENT_REVIEW":"provider.review_updated",
        "QUALIFICATION_APPROVED":"provider.approved",
        "QUALIFICATION_CONDITIONALLY_APPROVED":"provider.approved",
        "QUALIFICATION_REJECTED":"provider.rejected",
        "RESTRICTION_IMPOSED":"provider.scope_restricted",
        "RESTRICTION_LIFTED":"provider.reinstated",
        "OVERDUE_PROVIDER_ESCALATED":"provider.overdue_escalation",
    }
    for row in _rows(db, """SELECT id,supplier_id,case_id,action
           FROM quality_provider_qualification_events WHERE amo_id=:amo
           ORDER BY occurred_at DESC LIMIT 500""",amo=amo):
        event=governance.get(row["action"])
        if event:
            count+=_queue(db,amo=amo,event=event,source="quality_governance",
                          source_id=row["case_id"] or row["supplier_id"],
                          stamp=row["id"],supplier=row["supplier_id"])
    for row in _rows(db, """SELECT id,supplier_id,event_type,source_identifier
         FROM external_provider_change_events WHERE amo_id=:amo
         ORDER BY created_at DESC LIMIT 500""",amo=amo):
        action=str(row["event_type"]).upper()
        event=("provider.site_capability_change" if "SITE" in action or "CAPABILITY" in action
               else "provider.registration" if "CREATE" in action and "PROVIDER" in action
               else None)
        if event:
            count+=_queue(db,amo=amo,event=event,source="provider_change",
                          source_id=row["supplier_id"],stamp=row["id"],supplier=row["supplier_id"])
    for row in _rows(db, """SELECT id,supplier_id,status,version,technical_state
        FROM quality_provider_qualification_cases WHERE amo_id=:amo
        AND status IN ('SUBMITTED','IN_REVIEW','READY','APPROVED','CONDITIONALLY_APPROVED','REJECTED')
        ORDER BY updated_at DESC LIMIT 200""",amo=amo):
        event=("provider.approved" if row["status"] in ("APPROVED","CONDITIONALLY_APPROVED")
               else "provider.rejected" if row["status"]=="REJECTED"
               else "provider.technical_review_pending" if row["technical_state"]=="PENDING"
               else "provider.quality_review_pending")
        count+=_queue(db,amo=amo,event=event,source="qualification_state",
                      source_id=row["id"],stamp=str(row["version"])+":"+row["status"],
                      supplier=row["supplier_id"],cancel_older=True)
    for row in _rows(db, """SELECT id,supplier_id,status,version FROM
           quality_external_provider_contracts WHERE amo_id=:amo
           AND status IN ('SUSPENDED','TERMINATED','PENDING','DRAFT')
           ORDER BY updated_at DESC LIMIT 150""",amo=amo):
        event=("contract.suspended_terminated" if row["status"] in ("SUSPENDED","TERMINATED")
               else "contract.review_pending")
        count+=_queue(db,amo=amo,event=event,source="agreement_state",
                      source_id=row["id"],stamp=f"{row['status']}:{row['version']}",
                      supplier=row["supplier_id"],cancel_older=True)
    for row in _rows(db, """SELECT i.rfq_id,i.supplier_id,i.invited_at
          FROM procurement_rfq_suppliers i JOIN procurement_rfqs r
          ON r.id=i.rfq_id AND r.amo_id=:amo
          WHERE i.invited_at IS NOT NULL AND r.amo_id=:amo
          ORDER BY i.invited_at DESC LIMIT 150""",amo=amo):
        count+=_queue(db,amo=amo,event="procurement.rfq_invited",source="rfq_invite",
                      source_id=row["rfq_id"],stamp=f"{row['supplier_id']}:{row['invited_at']}",
                      supplier=row["supplier_id"])
    return count


def _qms_grant_allows(grant, audit_id: str, capability: str) -> bool:
    """Recheck the exact assigned audit and operation on an active member grant."""
    scopes = grant.get("object_scope_json") or {}
    capabilities = set(grant.get("capabilities_json") or [])
    return (
        capability in capabilities
        and str(audit_id) in {str(item) for item in scopes.get("assignments", [])}
    )


def _scan_qms_provider_collaboration(db, amo):
    """Project canonical QMS notices and released CAR obligations to *assigned*
    provider members only. Staff continue using the existing QMS alerts.

    This creates no new audits, findings, CARs or approval decisions. All items
    are rechecked against their current canonical source before dispatch.
    """
    count = 0
    grants = _rows(db, """SELECT g.tenant_provider_id, g.object_scope_json,
        g.capabilities_json, m.identity_id, p.supplier_id, p.portal_state
        FROM external_tenant_grants g
        JOIN external_organization_memberships m ON m.id=g.membership_id
        JOIN external_identities i ON i.id=m.identity_id
        JOIN external_tenant_providers p ON p.id=g.tenant_provider_id
          AND p.amo_id=g.amo_id
        WHERE g.amo_id=:amo AND g.status='ACTIVE'
          AND m.status='ACTIVE' AND i.status='ACTIVE'
          AND p.portal_state IN ('ACTIVE','SUSPENDED')
        ORDER BY g.id LIMIT 1000""", amo=amo)
    if not grants:
        return 0

    # DELIVERED is a canonical QMS notice transition, not proof of email
    # delivery. Its database revision and status are rechecked at dispatch.
    notices = _rows(db, """SELECT n.id,n.audit_id,n.status,n.revision_no
        FROM quality_audit_notices n WHERE n.amo_id=:amo
          AND n.status='DELIVERED'
        ORDER BY n.notice_date DESC,n.id LIMIT 150""", amo=amo)
    for row in notices:
        for grant in grants:
            if grant["portal_state"] != "ACTIVE":
                continue
            if not _qms_grant_allows(grant, str(row["audit_id"]), "task.read"):
                continue
            count += _queue(
                db, amo=amo, event="quality.audit_notice",
                source="qms_notice", source_id=f"{row['audit_id']}:{row['id']}",
                stamp=f"{row['status']}:{row['revision_no']}",
                supplier=grant["supplier_id"], recipient_kind="provider",
                provider=grant["tenant_provider_id"], recipient_id=grant["identity_id"],
                cancel_older=True,
            )

    requests = _rows(db, """SELECT id,audit_id,status,due_date
        FROM quality_audit_document_requests
        WHERE amo_id=:amo AND status='REQUESTED'
        ORDER BY due_date NULLS LAST,id LIMIT 150""", amo=amo)
    for row in requests:
        for grant in grants:
            if grant["portal_state"] != "ACTIVE":
                continue
            if not _qms_grant_allows(grant, str(row["audit_id"]), "task.read"):
                continue
            count += _queue(
                db, amo=amo, event="quality.document_requested",
                source="qms_document_request", source_id=f"{row['audit_id']}:{row['id']}",
                stamp=f"{row['status']}:{row['due_date']}",
                supplier=grant["supplier_id"], recipient_kind="provider",
                provider=grant["tenant_provider_id"], recipient_id=grant["identity_id"],
                cancel_older=True,
            )

    # Only an expressly RELEASED finding enters the partner work queue.
    # A newer release/withdrawal event invalidates a previously queued alert.
    findings = _rows(db, """SELECT e.id,e.audit_id,e.finding_id
        FROM quality_audit_finding_release_events e
        WHERE e.amo_id=:amo AND e.action='RELEASED'
          AND e.id=(SELECT e2.id FROM quality_audit_finding_release_events e2
            WHERE e2.amo_id=e.amo_id AND e2.finding_id=e.finding_id
            ORDER BY e2.created_at DESC,e2.id DESC LIMIT 1)
        ORDER BY e.created_at DESC,e.id DESC LIMIT 150""", amo=amo)
    for row in findings:
        for grant in grants:
            if grant["portal_state"] != "ACTIVE":
                continue
            if not _qms_grant_allows(grant, str(row["audit_id"]), "task.read"):
                continue
            count += _queue(
                db, amo=amo, event="quality.finding_issued",
                source="qms_finding", source_id=f"{row['audit_id']}:{row['finding_id']}",
                stamp=row["id"], supplier=grant["supplier_id"],
                recipient_kind="provider", provider=grant["tenant_provider_id"],
                recipient_id=grant["identity_id"], cancel_older=True,
            )

    # CAR duty is derived from QMS's original released finding, not a new
    # external CAR table. Retain access to existing CARs during restrictions
    # where the member's corrective-action grant is still in force.
    cars = _rows(db, """SELECT c.id,c.status,c.due_date,f.audit_id
        FROM quality_cars c
        JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
        WHERE c.amo_id=:amo AND c.status NOT IN ('CLOSED','CANCELLED')
          AND c.due_date IS NOT NULL AND c.due_date <= CURRENT_DATE + 30
          AND (SELECT e.action FROM quality_audit_finding_release_events e
               WHERE e.amo_id=c.amo_id AND e.finding_id=f.id
               ORDER BY e.created_at DESC,e.id DESC LIMIT 1)='RELEASED'
        ORDER BY c.due_date,c.id LIMIT 150""", amo=amo)
    for row in cars:
        event = "quality.capa_overdue" if row["due_date"] < date.today() else "quality.car_due"
        for grant in grants:
            if not _qms_grant_allows(grant, str(row["audit_id"]), "capa.respond"):
                continue
            count += _queue(
                db, amo=amo, event=event,
                source="qms_car", source_id=f"{row['audit_id']}:{row['id']}",
                stamp=f"{row['status']}:{row['due_date']}",
                supplier=grant["supplier_id"], recipient_kind="provider",
                provider=grant["tenant_provider_id"], recipient_id=grant["identity_id"],
                cancel_older=True,
            )
    return count


def _scan_partner_records(db, amo):
    """Project provider-owned evidence/proposals/contract acknowledgements.

    These are authoritative committed partner rows. A proposal or receipt
    never grants scope, signs a contract, or marks evidence Quality-verified.
    """
    count=0
    for item in _rows(db, """SELECT x.id,x.category,x.status,x.version,p.supplier_id
        FROM external_partner_change_requests x
        JOIN external_tenant_providers p
          ON p.id=x.tenant_provider_id AND p.amo_id=x.amo_id
        WHERE x.amo_id=:amo AND x.category IN ('SITE','CAPABILITY')
          AND x.status IN ('PENDING','UNDER_REVIEW')
        ORDER BY x.created_at DESC LIMIT 300""",amo=amo):
        count+=_queue(db,amo=amo,event="provider.site_capability_proposed",
                      source="partner_change",source_id=item["id"],
                      stamp=f"{item['status']}:{item['version']}",
                      supplier=item["supplier_id"],cancel_older=True)
    for item in _rows(db, """SELECT x.id,x.status,p.supplier_id
        FROM external_partner_evidence_submissions x
        JOIN external_tenant_providers p
          ON p.id=x.tenant_provider_id AND p.amo_id=x.amo_id
        WHERE x.amo_id=:amo AND x.status IN
          ('PENDING_REVIEW','ACCEPTED','REJECTED')
        ORDER BY x.created_at DESC LIMIT 350""",amo=amo):
        event={"PENDING_REVIEW":"quality.evidence_received",
               "ACCEPTED":"quality.evidence_reviewed",
               "REJECTED":"quality.evidence_rejected"}[item["status"]]
        count+=_queue(db,amo=amo,event=event,source="partner_evidence",
                      source_id=item["id"],stamp=item["status"],
                      supplier=item["supplier_id"],cancel_older=True)
    for item in _rows(db, """SELECT x.id,x.contract_id,x.supplier_id,
             x.acknowledgement
        FROM external_partner_contract_receipts x
        WHERE x.amo_id=:amo ORDER BY x.created_at DESC LIMIT 200""",amo=amo):
        event=("contract.acknowledged" if item["acknowledgement"]=="RECEIVED"
               else "contract.clarification_requested")
        count+=_queue(db,amo=amo,event=event,source="partner_contract",
                      source_id=item["contract_id"],stamp=item["id"],
                      supplier=item["supplier_id"])
    return count


def _scan_canonical_procurement(db, amo):
    """Map canonical Procurement transactions to alerts without inventing stock events."""
    count=0
    event_map={
        ("ProcurementQuote","receive"):"procurement.quote_received",
        ("ProcurementPurchaseOrder","send"):"procurement.po_issued",
        ("ProcurementPurchaseOrder","acknowledge"):"procurement.po_acknowledged",
        ("ProcurementReceipt","receive_to_quarantine"):"procurement.material_received",
        ("ProcurementReceipt","quality_release"):"procurement.quality_released",
        ("ProcurementQualityHold","place"):"procurement.quality_hold",
        ("ProcurementQualityHold","release"):"procurement.quality_released",
    }
    for item in _rows(db, """SELECT id,entity_type,entity_id,action,detail
        FROM procurement_events WHERE amo_id=:amo
        ORDER BY occurred_at DESC,id DESC LIMIT 450""",amo=amo):
        kind=item["entity_type"]
        action=item["action"]
        event=event_map.get((kind,action))
        if kind=="ProcurementReceipt" and action=="inspect":
            detail=item["detail"]
            if isinstance(detail,str):
                try:
                    detail=json.loads(detail)
                except (ValueError,TypeError):
                    detail={}
            disposition=detail.get("disposition") if isinstance(detail,dict) else None
            if disposition in ("REJECTED","RETURN_TO_SUPPLIER","ESCALATED_TO_QUALITY","ON_HOLD"):
                event="procurement.inspection_discrepancy"
            elif disposition in ("ACCEPTED","CONDITIONALLY_ACCEPTED"):
                event="procurement.inspection_completed"
            else:
                # Unknown or newly introduced outcomes are not proof of
                # completed inspection or release.
                event=None
        if not event:
            continue
        count+=_queue(db,amo=amo,event=event,source="procurement_canonical",
                      source_id=f"{kind}:{item['entity_id']}",stamp=item["id"])
    return count

def _scan_contracted_work_deadlines(db,amo,local_now,zone,policy):
    """Optional manager-controlled dates in Phase 7 written requirements."""
    count=0
    today=_local_day(local_now,zone)
    for row in _rows(db, """SELECT id,supplier_id,status,requirements_json,updated_at
       FROM external_contracted_work WHERE amo_id=:amo
       AND status NOT IN ('CLOSED','CANCELLED') ORDER BY updated_at DESC LIMIT 400""",amo=amo):
        requirements=row["requirements_json"] or {}
        for field,event,state in (
            ("provider_ack_due_at","maintenance.ack_overdue",{"DISPATCHED"}),
            ("expected_completion_at","maintenance.completion_missed",
             {"DISPATCHED","PROVIDER_ACCEPTED","IN_PROGRESS","ADDITIONAL_WORK_REQUESTED","ON_HOLD"}),
        ):
            if row["status"] not in state or not requirements.get(field):
                continue
            try:
                due=datetime.fromisoformat(str(requirements[field]).replace("Z","+00:00"))
                if due.tzinfo is None:due=due.replace(tzinfo=zone)
                due_date=due.astimezone(zone).date()
            except (ValueError,TypeError,OverflowError):
                continue
            for overdue in policy["escalation_days_json"].get(CATALOG[event],[]):
                trigger=due_date+timedelta(days=overdue)
                if trigger!=today:
                    continue
                # A missed deadline must not be announced before the
                # actual promised timestamp on the same local day.
                at=datetime.combine(trigger,time(8),zone)
                if overdue==0:
                    at=max(at,due.astimezone(zone))
                count+=_queue(db,amo=amo,event=event,source="maintenance_due",
                              source_id=row["id"],stamp=f"{field}:{requirements[field]}:{overdue}",
                              supplier=row["supplier_id"],due=at.astimezone(timezone.utc),
                              cancel_older=True)
    return count

def _allowed_link(amo_code, row):
    from urllib.parse import quote
    code=quote(str(amo_code),safe="")
    source=row["source_kind"]
    supplier=row["supplier_id"]
    source_id=str(row["source_id"]).split(":")[0]
    if source in ("certificate","capability","evidence","qualification","agreement","surveillance","quality_governance","qualification_state","provider_change","agreement_state") and supplier:
        tab=("contracts" if source in ("agreement","agreement_state") else "qualification"
             if source in ("qualification","qualification_state","quality_governance","surveillance") else "evidence")
        return "/maintenance/"+code+"/quality/suppliers/"+str(int(supplier))+"/"+tab
    if source in ("partner_change","partner_evidence","partner_contract") and supplier:
        tab="contracts" if source=="partner_contract" else "evidence"
        return "/maintenance/"+code+"/quality/suppliers/"+str(int(supplier))+"/"+tab
    if source in ("qms_notice", "qms_document_request", "qms_finding"):
        return "/maintenance/"+code+"/quality/audits/"+quote(source_id,safe="")
    if source=="qms_car":
        return "/maintenance/"+code+"/quality/cars/"+quote(str(row["source_id"]).partition(":")[2],safe="")
    if source=="procurement_canonical":
        entity, _, record_id=str(row["source_id"]).partition(":")
        section=({"ProcurementRFQ":"sourcing","ProcurementQuote":"sourcing",
                  "ProcurementPurchaseOrder":"orders","ProcurementReceipt":"receiving",
                  "ProcurementQualityHold":"control"}.get(entity,"command"))
        return ("/maintenance/"+code+"/procurement/"+section+"?recordKind="+
                quote(entity,safe="")+"&recordId="+quote(record_id,safe=""))
    if source in ("maintenance_event","maintenance_due"):
        return "/maintenance/"+code+"/contracted-work?work="+quote(source_id,safe="")
    if source in ("procurement_event","rfq","po_delivery","po_ack"):
        section="sourcing" if source=="rfq" else "collaboration"
        return ("/maintenance/"+code+"/procurement/"+section+
                "?providerRecord="+quote(source_id,safe=""))
    return "/maintenance/"+code+"/quality/suppliers"

def _still_current(db, amo, row, zone, policy):
    source=row["source_kind"]
    # Action-needed projections must not survive source closure or review.
    # Historical immutable transition events are retained separately.
    if source in {"qms_notice", "qms_document_request", "qms_finding", "qms_car"}:
        audit_id, separator, object_id = str(row["source_id"]).partition(":")
        if not separator or not audit_id or not object_id:
            return False
        if source == "qms_notice":
            found = db.execute(text("""SELECT status,revision_no FROM quality_audit_notices
                WHERE amo_id=:amo AND audit_id=:audit AND id=:id"""),
                {"amo": amo, "audit": audit_id, "id": object_id}).mappings().first()
            return bool(found and found["status"] == "DELIVERED"
                        and row["source_stamp"] == f"{found['status']}:{found['revision_no']}")
        if source == "qms_document_request":
            found = db.execute(text("""SELECT status,due_date FROM quality_audit_document_requests
                WHERE amo_id=:amo AND audit_id=:audit AND id=:id"""),
                {"amo": amo, "audit": audit_id, "id": object_id}).mappings().first()
            return bool(found and found["status"] == "REQUESTED"
                        and row["source_stamp"] == f"{found['status']}:{found['due_date']}")
        if source == "qms_finding":
            found = db.execute(text("""SELECT id,action FROM quality_audit_finding_release_events
                WHERE amo_id=:amo AND audit_id=:audit AND finding_id=:id
                ORDER BY created_at DESC,id DESC LIMIT 1"""),
                {"amo": amo, "audit": audit_id, "id": object_id}).mappings().first()
            return bool(found and found["action"] == "RELEASED"
                        and str(row["source_stamp"]) == str(found["id"]))
        found = db.execute(text("""SELECT c.status,c.due_date FROM quality_cars c
            JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
            WHERE c.amo_id=:amo AND f.audit_id=:audit AND c.id=:id
              AND (SELECT e.action FROM quality_audit_finding_release_events e
                   WHERE e.amo_id=c.amo_id AND e.finding_id=f.id
                   ORDER BY e.created_at DESC,e.id DESC LIMIT 1)='RELEASED'"""),
            {"amo": amo, "audit": audit_id, "id": object_id}).mappings().first()
        return bool(found and found["status"] not in {"CLOSED","CANCELLED"}
                    and found["due_date"] is not None
                    and row["source_stamp"] == f"{found['status']}:{found['due_date']}")
    if source=="partner_change":
        current=db.execute(text("""SELECT status,version FROM external_partner_change_requests
            WHERE amo_id=:amo AND id=:id"""),{"amo":amo,"id":row["source_id"]}).mappings().first()
        return bool(current and current["status"] in ("PENDING","UNDER_REVIEW")
                    and row["source_stamp"]==f"{current['status']}:{current['version']}")
    if source=="partner_evidence":
        current=db.execute(text("""SELECT status FROM external_partner_evidence_submissions
            WHERE amo_id=:amo AND id=:id"""),{"amo":amo,"id":row["source_id"]}).scalar()
        return bool(current and current==row["source_stamp"])
    if source=="qualification_state":
        current=db.execute(text("""SELECT status,version FROM quality_provider_qualification_cases
            WHERE amo_id=:amo AND id=:id"""),{"amo":amo,"id":row["source_id"]}).mappings().first()
        return bool(current and row["source_stamp"]==str(current["version"])+":"+current["status"])
    if source=="agreement_state":
        current=db.execute(text("""SELECT status,version FROM quality_external_provider_contracts
            WHERE amo_id=:amo AND id=:id"""),{"amo":amo,"id":row["source_id"]}).mappings().first()
        return bool(current and row["source_stamp"]==f"{current['status']}:{current['version']}")
    if source in DATE_SOURCES:
        current=_active_source(db,amo,source,row["source_id"])
        if not current:
            return False
        actual=_date_in_tenant_zone(current["due"],zone)
        # Stamp starts with a fixed YYYY-MM-DD date from authoritative data.
        stamp=str(row["source_stamp"])
        if not actual or not stamp.startswith(actual.isoformat()+":"):
            return False
        parts=stamp.split(":")
        milestone=parts[1] if len(parts)>1 else ""
        if milestone in ("lead","overdue"):
            try:
                offset=int(parts[2])
            except (ValueError,IndexError):
                return False
            department=CATALOG[row["event_key"]]
            group="lead_days_json" if milestone=="lead" else "escalation_days_json"
            return offset in policy[group].get(department,[])
        if source=="agreement" and milestone=="notice":
            days=db.execute(text("""SELECT termination_notice_days
                FROM quality_external_provider_contracts
                WHERE amo_id=:amo AND id=:id"""),
                {"amo":amo,"id":str(row["source_id"]).split(":")[0]}).scalar()
            return days is not None and len(parts)>2 and str(days)==parts[2]
        return False
    if source=="po_ack":
        found=db.execute(text("""SELECT id FROM procurement_purchase_orders
             WHERE amo_id=:amo AND id=:id AND sent_at IS NOT NULL
             AND supplier_ack_reference IS NULL AND acknowledged_at IS NULL
             AND status NOT IN ('CANCELLED','CLOSED','ACKNOWLEDGED','FULFILLED')"""),
             {"amo":amo,"id":row["source_id"]}).first()
        return found is not None
    if source=="maintenance_due":
        result=db.execute(text("""SELECT status,requirements_json FROM external_contracted_work
            WHERE amo_id=:amo AND id=:id"""),{"amo":amo,"id":row["source_id"]}).mappings().first()
        if not result:
            return False
        requirements=result["requirements_json"] or {}
        allowed={
            "provider_ack_due_at": {"DISPATCHED"},
            "expected_completion_at": {"DISPATCHED","PROVIDER_ACCEPTED","IN_PROGRESS",
                                       "ADDITIONAL_WORK_REQUESTED","ON_HOLD"},
        }
        # Completed acknowledgement, changed ETA or closure supersedes
        # outstanding reminders even when the old scheduled date persists.
        return any(result["status"] in states
                   and str(row["source_stamp"]).startswith(f"{field}:{requirements.get(field)}:")
                   for field,states in allowed.items() if requirements.get(field))
    return True


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
    query = """SELECT * FROM external_provider_alert_jobs WHERE amo_id=:amo
       AND status IN ('PENDING','RETRY') AND due_at<=:now
       AND (next_attempt_at IS NULL OR next_attempt_at<=:now)
       ORDER BY due_at,id LIMIT 100"""
    if db.get_bind().dialect.name=="postgresql":
        query += " FOR UPDATE SKIP LOCKED"
    jobs=_rows(db,query,amo=amo,now=now)
    for job in jobs:
        savepoint = db.begin_nested()
        try:
            if not _still_current(db,amo,job,zone,policy):
                db.execute(text("""UPDATE external_provider_alert_jobs
                    SET status='CANCELLED',cancelled_at=NOW(),updated_at=NOW()
                    WHERE id=:id"""),{"id":job["id"]})
                savepoint.commit()
                continue
            recipient = None
            vendor_email = None
            vendor_email_enabled = False
            vendor_digest_enabled = False
            if job["recipient_user_id"]:
                recipient = db.query(accounts.User).filter(
                    accounts.User.amo_id==amo,
                    accounts.User.id==job["recipient_user_id"],
                    accounts.User.is_active.is_(True)).first()
                if recipient is None or str(getattr(recipient.role,"value",recipient.role)) not in policy["routes_json"].get(CATALOG[job["event_key"]],[]):
                    db.execute(text("""UPDATE external_provider_alert_jobs
                         SET status='CANCELLED',cancelled_at=NOW() WHERE id=:id"""), {"id":job["id"]})
                    savepoint.commit()
                    continue
            elif job["recipient_identity_id"]:
                # Never deliver to revoked identities or grants. A vendor may
                # only receive a scoped record; no generic supplier-wide broadcast.
                grant = _rows(db, """SELECT g.object_scope_json,g.capabilities_json,i.email,i.verified_at
                   FROM external_tenant_grants g
                   JOIN external_organization_memberships m ON m.id=g.membership_id
                   JOIN external_identities i ON i.id=m.identity_id
                   JOIN external_tenant_providers p ON p.id=g.tenant_provider_id
                      AND p.amo_id=g.amo_id
                   WHERE g.amo_id=:amo AND g.tenant_provider_id=:provider
                   AND i.id=:identity AND g.status='ACTIVE' AND m.status='ACTIVE'
                   AND i.status='ACTIVE'
                   AND (p.portal_state='ACTIVE'
                     OR (p.portal_state='SUSPENDED' AND :car_remediation=true))""", amo=amo,
                   provider=job["recipient_provider_id"],
                   identity=job["recipient_identity_id"],
                   car_remediation=job["source_kind"]=="qms_car")
                source_kind = job["source_kind"]
                scope_kind = ("contracted_work" if source_kind == "maintenance_event"
                              else "assignments" if source_kind.startswith("qms_")
                              else "procurement")
                scoped_id = (str(job["source_id"]).partition(":")[0]
                             if source_kind.startswith("qms_") else str(job["source_id"]))
                required_capability = ("capa.respond" if source_kind == "qms_car"
                    else "task.read" if source_kind.startswith("qms_") else None)
                assigned = any(
                    scoped_id in {str(v) for v in (g["object_scope_json"] or {}).get(scope_kind, [])}
                    and (not required_capability
                        or required_capability in (g.get("capabilities_json") or []))
                    for g in grant
                )
                if not assigned:
                    db.execute(text("""UPDATE external_provider_alert_jobs
                         SET status='CANCELLED',cancelled_at=NOW() WHERE id=:id"""), {"id":job["id"]})
                    savepoint.commit()
                    continue
                # Email requires a verified external identity, current grant,
                # active provider account and explicit member opt-in.
                if grant[0]["verified_at"]:
                    vendor_email = grant[0]["email"]
            else:
                savepoint.commit()
                continue
            # Sensitive descriptions, evidence names, internal notes and
            # object-store URLs are deliberately absent from notification text.
            default_message = "External provider action: " + job["event_key"].replace(".", " / ").replace("_", " ")
            configured = str(policy["templates_json"].get(job["event_key"]) or "").strip()
            # Tenant-editable content is only a short label; never interpolate
            # user-provided markup, document bodies or confidential payloads.
            message = configured if configured else default_message
            label = "Review assigned provider record"
            channels = policy["channels_json"].get(CATALOG[job["event_key"]], {"in_app":True,"email":False})
            partner_in_app = True
            if job["recipient_identity_id"]:
                preference = db.execute(text("""SELECT in_app_enabled,email_enabled,digest_enabled
                    FROM external_provider_alert_preferences
                    WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:identity"""),
                    {"amo":amo,"provider":job["recipient_provider_id"],
                     "identity":job["recipient_identity_id"]}).mappings().first()
                partner_in_app = not preference or preference["in_app_enabled"] is not False
                vendor_email_enabled = bool(preference and preference["email_enabled"])
                vendor_digest_enabled = bool(preference and preference["digest_enabled"])
            if not channels.get("in_app",True) and not channels.get("email",False):
                db.execute(text("""UPDATE external_provider_alert_jobs
                    SET status='CANCELLED',cancelled_at=NOW(),updated_at=NOW()
                    WHERE id=:id"""),{"id":job["id"]})
                savepoint.commit()
                continue
            if not job["in_app_id"] and channels.get("in_app", True) and partner_in_app:
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
            email_on = bool(channels.get("email",False) and (
                recipient is not None or (vendor_email and vendor_email_enabled)))
            if not (channels.get("in_app",True) and partner_in_app) and not email_on:
                db.execute(text("""UPDATE external_provider_alert_jobs
                    SET status='CANCELLED',cancelled_at=NOW(),updated_at=NOW()
                    WHERE id=:id"""),{"id":job["id"]})
                savepoint.commit()
                continue
            if email_on:
                local = now.astimezone(zone)
                digest = policy["digest_json"]
                # Both the tenant's digest window and the partner's opted-in
                # preference must be respected. A source arriving after today's
                # window waits for the next local day's window; if quiet hours
                # overlap that window, delivery resumes once quiet time ends.
                # Requiring local.hour == digest_hour would strand such jobs.
                digest_applies = bool(digest.get("enabled") or vendor_digest_enabled)
                digest_blocked = False
                if digest_applies:
                    due_utc = _utc(job["due_at"])
                    if due_utc is None:
                        raise ValueError("Invalid source due timestamp")
                    due_local = due_utc.astimezone(zone)
                    hour = int(digest.get("hour", 8))
                    eligible_at = datetime.combine(due_local.date(), time(hour, 0), zone)
                    if due_local > eligible_at:
                        eligible_at = datetime.combine(
                            due_local.date() + timedelta(days=1), time(hour, 0), zone)
                    digest_blocked = local < eligible_at
                blocked = (_restricted_now(local,policy["quiet_hours_json"])
                           or digest_blocked)
                if blocked:
                    retry = now+timedelta(hours=1)
                    db.execute(text("""UPDATE external_provider_alert_jobs SET
                        status='RETRY',next_attempt_at=:retry,updated_at=NOW()
                        WHERE id=:id"""),{"retry":retry,"id":job["id"]})
                    savepoint.commit()
                    continue
                if recipient:
                    recipient_address = getattr(recipient,"email",None)
                    action_url = _allowed_link(code,job)
                else:
                    from urllib.parse import quote
                    recipient_address = vendor_email
                    action_url = ("/partner/" + quote(str(code),safe="") +
                                  "/work?work=" + quote(str(job["source_id"]),safe=""))
                email = mail_service.send_email("provider.lifecycle",recipient_address,
                    "External provider action requires review",
                    {"summary":message, "url":action_url},
                    job["fingerprint"]+":"+str(job["attempts"]),
                    amo_id=amo,db=db,
                    recipient_user_id=str(recipient.id) if recipient else None,
                    audit_context={"event_key":job["event_key"],"job_id":job["id"]})
                db.execute(text("""UPDATE external_provider_alert_jobs
                   SET email_log_id=:log WHERE id=:id"""),{"log":str(email.id),"id":job["id"]})
                delivery_state = str(getattr(email.status,"value",email.status))
                if delivery_state=="SKIPPED_BY_PREFERENCE":
                    # An email suppressed by existing user preferences
                    # is not counted as a delivered email. A valid in-app
                    # notice may still be visible in the shared center.
                    has_notice=bool(job["in_app_id"] or (
                        channels.get("in_app",True) and partner_in_app))
                    db.execute(text("""UPDATE external_provider_alert_jobs SET
                        status=:status,delivered_at=CASE WHEN :notice THEN NOW()
                          ELSE NULL END,updated_at=NOW() WHERE id=:id"""),
                        {"status":"DELIVERED" if has_notice else "CANCELLED",
                         "notice":has_notice,"id":job["id"]})
                    savepoint.commit()
                    continue
                if delivery_state in ("FAILED","SKIPPED_NO_PROVIDER","QUEUED"):
                    attempts=int(job["attempts"])+1
                    db.execute(text("""UPDATE external_provider_alert_jobs
                      SET status=:status, attempts=:attempts, last_error=:error,
                          next_attempt_at=:next,updated_at=NOW() WHERE id=:id"""),
                      {"status":"FAILED" if attempts>=8 else "RETRY","attempts":attempts,
                       "error":("Email not accepted by configured provider: "+delivery_state)[:500],
                       "next":now+timedelta(minutes=min(1440,2**min(attempts,10))),
                       "id":job["id"]})
                    savepoint.commit()
                    continue
            db.execute(text("""UPDATE external_provider_alert_jobs SET status='DELIVERED',
                  delivered_at=NOW(),next_attempt_at=NULL,last_error=NULL,updated_at=NOW()
                  WHERE id=:id"""),{"id":job["id"]})
            delivered += 1
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
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
                report["enqueued"] += _scan_partner_records(db,str(amo))
                report["enqueued"] += _scan_qms_provider_collaboration(db,str(amo))
                report["enqueued"] += _scan_canonical_procurement(db,str(amo))
                report["enqueued"] += _schedule_expiries(db,str(amo),now,zone,policy)
                report["enqueued"] += _scan_contracted_work_deadlines(db,str(amo),now,zone,policy)
                report["dispatched"] += _dispatch(db,str(amo),code,zone,policy,now)
                db.commit()
                report["tenants"] += 1
            except Exception:
                db.rollback()
                report["failed_tenants"] += 1
                LOGGER.exception("Phase 8 provider alert tenant scan failed %s",amo)
    return report
