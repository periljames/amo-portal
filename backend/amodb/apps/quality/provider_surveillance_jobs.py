"""Phase 4 periodic provider due-review notifications via the existing scheduled worker.

No parallel daemon, audit engine or CAR escalation system. Canonical QMS CAR
reminders continue to own their overdue-action escalation. This scan concerns
tenant-approved qualification/surveillance review dates only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text

from amodb import storage
from amodb.database import SessionLocal
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models as quality
from amodb.apps.quality.tenant_security import set_postgres_tenant_context

LOG = logging.getLogger(__name__)


def scan_due_provider_reviews() -> dict[str, int]:
    """Send at most one reminder per Quality Manager, case, and seven days."""
    result={"tenants":0,"due_reviews":0,"due_documents":0,"due_contracts":0,"notifications":0,"expired_uploads":0}
    with SessionLocal() as db:
        if not inspect(db.get_bind()).has_table("quality_provider_qualification_cases"):
            return result
        tenants=db.query(accounts.AMO.id,accounts.AMO.amo_code).filter(
            accounts.AMO.is_active.is_(True)).all()
        db.rollback()
        for amo_id, amo_code in tenants:
            try:
                set_postgres_tenant_context(db,amo_id=str(amo_id),user_id="")
                if db.get_bind().dialect.name=="postgresql":
                    # Internal scheduled Quality governance requires explicit
                    # provider staging FORCE-RLS visibility after tenant scoping.
                    db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
                cases=db.execute(text("""
                    SELECT q.id,q.supplier_id,q.category,s.legal_name,q.next_review_due_on
                    FROM quality_provider_qualification_cases q JOIN procurement_suppliers s
                    ON s.amo_id=q.amo_id AND s.id=q.supplier_id
                    WHERE q.amo_id=:amo
                    AND q.status IN ('APPROVED','CONDITIONALLY_APPROVED')
                    AND q.next_review_due_on<=CURRENT_DATE
                    AND NOT EXISTS (
                        SELECT 1 FROM quality_provider_qualification_cases newer
                        WHERE newer.amo_id=q.amo_id AND newer.supplier_id=q.supplier_id
                        AND newer.created_at>q.created_at
                        AND newer.status IN ('APPROVED','CONDITIONALLY_APPROVED')
                    )
                    ORDER BY q.next_review_due_on,q.id LIMIT 200
                """),{"amo":str(amo_id)}).mappings().all()
                alerts_active=inspect(db.get_bind()).has_table("external_provider_alert_jobs")
                managers=db.query(accounts.User).filter(
                    accounts.User.amo_id==str(amo_id),
                    accounts.User.role==accounts.AccountRole.QUALITY_MANAGER,
                    accounts.User.is_active.is_(True)).limit(25).all()
                if alerts_active:
                    # Phase 8 owns these expiries; preserve upload fragment cleanup
                    # and avoid posting duplicate legacy QMS notifications.
                    managers=[]
                cutoff=datetime.now(timezone.utc)-timedelta(days=7)
                for row in cases:
                    result["due_reviews"]+=1
                    for manager in managers:
                        existing=db.query(quality.QMSNotification.id).filter(
                            quality.QMSNotification.amo_id==str(amo_id),
                            quality.QMSNotification.user_id==str(manager.id),
                            quality.QMSNotification.entity_type=="provider_qualification_review",
                            quality.QMSNotification.entity_id==str(row["id"]),
                            quality.QMSNotification.created_at>=cutoff).first()
                        if existing:continue
                        db.add(quality.QMSNotification(
                            amo_id=str(amo_id),user_id=str(manager.id),
                            severity=quality.QMSNotificationSeverity.ACTION_REQUIRED,
                            message="Provider qualification review is overdue: "+str(row["legal_name"])+
                                " ("+str(row["category"])+").",
                            action_url="/maintenance/"+str(amo_code)+"/quality/suppliers/"+
                                str(row["supplier_id"])+"/qualification",
                            action_label="Review provider qualification",
                            entity_type="provider_qualification_review",entity_id=str(row["id"])))
                        result["notifications"]+=1
                # Phase 5 reuses this existing bounded tenant-scoped scheduled job
                # and QMS notification register. No universal document retention
                # or renewal interval is imposed: configured dates/notice windows
                # on canonical QMS evidence and agreements drive these reminders.
                if inspect(db.get_bind()).has_table("external_provider_document_requirements"):
                    due_evidence=db.execute(text("""
                        SELECT e.id, s.legal_name, e.title, e.valid_until
                        FROM quality_external_provider_evidence e
                        JOIN procurement_suppliers s ON s.amo_id=e.amo_id AND s.id=e.supplier_id
                        JOIN external_partner_evidence_submissions staging
                          ON staging.amo_id=e.amo_id AND staging.qms_evidence_id=e.id
                        JOIN external_provider_document_requirements req
                          ON req.amo_id=staging.amo_id AND req.id=staging.requirement_id
                        WHERE e.amo_id=:amo AND e.status='VERIFIED'
                          AND req.enabled=true AND req.expiry_required=true
                          AND e.valid_until IS NOT NULL
                          AND e.valid_until <= CURRENT_DATE+req.reminder_days*INTERVAL '1 day'
                        ORDER BY e.valid_until,e.id LIMIT 150
                    """),{"amo":str(amo_id)}).mappings().all()
                    # Once a contract's notice window opens, alert its owner.
                    # Zero or absent notice period means no inferred early notice.
                    due_contracts=db.execute(text("""
                        SELECT c.id,c.contract_number,s.legal_name,c.expires_on
                        FROM quality_external_provider_contracts c
                        JOIN procurement_suppliers s ON s.amo_id=c.amo_id AND s.id=c.supplier_id
                        WHERE c.amo_id=:amo AND c.status='ACTIVE'
                          AND c.expires_on IS NOT NULL
                          AND c.termination_notice_days IS NOT NULL
                          AND c.expires_on <= CURRENT_DATE+c.termination_notice_days*INTERVAL '1 day'
                        ORDER BY c.expires_on,c.id LIMIT 150
                    """),{"amo":str(amo_id)}).mappings().all()
                    result["due_documents"]+=len(due_evidence)
                    result["due_contracts"]+=len(due_contracts)
                    for manager in managers:
                        for kind, rows in (("provider_document_expiry",due_evidence),
                                           ("provider_agreement_notice",due_contracts)):
                            for row in rows:
                                existing=db.query(quality.QMSNotification.id).filter(
                                    quality.QMSNotification.amo_id==str(amo_id),
                                    quality.QMSNotification.user_id==str(manager.id),
                                    quality.QMSNotification.entity_type==kind,
                                    quality.QMSNotification.entity_id==str(row["id"]),
                                    quality.QMSNotification.created_at>=cutoff).first()
                                if existing:continue
                                subject=str(row["title"] if kind=="provider_document_expiry" else row["contract_number"])
                                db.add(quality.QMSNotification(
                                    amo_id=str(amo_id),user_id=str(manager.id),
                                    severity=quality.QMSNotificationSeverity.ACTION_REQUIRED,
                                    message=("Provider document expiry/review: " if kind=="provider_document_expiry"
                                      else "Provider maintenance agreement renewal/notice: ")+
                                      str(row["legal_name"])+" / "+subject+
                                      " (date "+str(row["valid_until"] if kind=="provider_document_expiry" else row["expires_on"])+")",
                                    action_url="/maintenance/"+str(amo_code)+"/quality/suppliers",
                                    action_label="Review governed provider records",
                                    entity_type=kind,entity_id=str(row["id"])))
                                result["notifications"]+=1
                # Recoverable transfer fragments are temporary. Expired
                # manifests remain for traceability, but orphaned part objects
                # must not consume tenants' storage indefinitely.
                if inspect(db.get_bind()).has_table("external_provider_upload_sessions"):
                    expired=db.execute(text("""
                        SELECT id,state FROM external_provider_upload_sessions
                        WHERE amo_id=:amo AND state IN ('OPEN','COMPLETED')
                          AND created_at < NOW()-INTERVAL '24 hours'
                        ORDER BY created_at,id LIMIT 100 FOR UPDATE SKIP LOCKED
                    """),{"amo":str(amo_id)}).mappings().all()
                    for upload in expired:
                        part_rows=db.execute(text("""
                            SELECT object_uri FROM external_provider_upload_parts
                            WHERE amo_id=:amo AND session_id=:id
                        """),{"amo":str(amo_id),"id":upload["id"]}).mappings().all()
                        try:
                            for part in part_rows:
                                storage.delete(part["object_uri"])
                        except Exception:
                            LOG.exception("Unable to clean expired provider upload %s",upload["id"])
                            continue
                        db.execute(text("""DELETE FROM external_provider_upload_parts
                            WHERE amo_id=:amo AND session_id=:id"""),
                            {"amo":str(amo_id),"id":upload["id"]})
                        if upload["state"]=="OPEN":
                            db.execute(text("""UPDATE external_provider_upload_sessions
                                SET state='EXPIRED',updated_at=NOW()
                                WHERE amo_id=:amo AND id=:id AND state='OPEN'"""),
                                {"amo":str(amo_id),"id":upload["id"]})
                            result["expired_uploads"]+=1
                db.commit()
                result["tenants"]+=1
            except Exception:
                db.rollback()
                LOG.exception("Provider surveillance alert scan failed for tenant %s",amo_id)
    return result
