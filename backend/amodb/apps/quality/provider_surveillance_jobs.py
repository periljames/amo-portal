"""Phase 4 periodic provider due-review notifications via the existing scheduled worker.

No parallel daemon, audit engine or CAR escalation system. Canonical QMS CAR
reminders continue to own their overdue-action escalation. This scan concerns
tenant-approved qualification/surveillance review dates only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text

from amodb.database import SessionLocal
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models as quality
from amodb.apps.quality.tenant_security import set_postgres_tenant_context

LOG = logging.getLogger(__name__)


def scan_due_provider_reviews() -> dict[str, int]:
    """Send at most one reminder per Quality Manager, case, and seven days."""
    result={"tenants":0,"due_reviews":0,"notifications":0}
    with SessionLocal() as db:
        if not inspect(db.get_bind()).has_table("quality_provider_qualification_cases"):
            return result
        tenants=db.query(accounts.AMO.id,accounts.AMO.amo_code).filter(
            accounts.AMO.is_active.is_(True)).all()
        db.rollback()
        for amo_id, amo_code in tenants:
            try:
                set_postgres_tenant_context(db,amo_id=str(amo_id),user_id="")
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
                managers=db.query(accounts.User).filter(
                    accounts.User.amo_id==str(amo_id),
                    accounts.User.role==accounts.AccountRole.QUALITY_MANAGER,
                    accounts.User.is_active.is_(True)).limit(25).all()
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
                db.commit()
                result["tenants"]+=1
            except Exception:
                db.rollback()
                LOG.exception("Provider surveillance alert scan failed for tenant %s",amo_id)
    return result
