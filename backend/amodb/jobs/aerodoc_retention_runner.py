from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.database import WriteSessionLocal
from amodb.apps.quality import models as quality_models
from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services


def run_retention_cycle() -> int:
    db = WriteSessionLocal()
    archived = 0
    try:
        now = datetime.now(timezone.utc)
        cutoff_5y = now - timedelta(days=365 * 5)
        rows = (
            db.query(quality_models.QMSDocumentRevision)
            .join(quality_models.QMSDocument, quality_models.QMSDocument.id == quality_models.QMSDocumentRevision.document_id)
            .filter(
                quality_models.QMSDocument.retention_category == quality_models.QMSRetentionCategory.MAINT_RECORD_5Y,
                quality_models.QMSDocumentRevision.created_at < cutoff_5y,
                quality_models.QMSDocumentRevision.primary_storage_provider != "cold_storage",
            )
            .all()
        )
        for rev in rows:
            rev.primary_storage_provider = "cold_storage"

            amo_id = None
            owner_user_id = getattr(rev.document, "owner_user_id", None)
            if owner_user_id:
                owner = db.query(account_models.User).filter(account_models.User.id == owner_user_id).first()
                if owner and owner.amo_id:
                    amo_id = owner.amo_id
            if not amo_id and rev.created_by_user_id:
                creator = db.query(account_models.User).filter(account_models.User.id == rev.created_by_user_id).first()
                if creator and creator.amo_id:
                    amo_id = creator.amo_id
            if not amo_id and rev.approved_by_user_id:
                approver = db.query(account_models.User).filter(account_models.User.id == rev.approved_by_user_id).first()
                if approver and approver.amo_id:
                    amo_id = approver.amo_id

            if amo_id:
                audit_services.log_event(
                    db,
                    amo_id=amo_id,
                    actor_user_id=None,
                    entity_type="qms.document.revision",
                    entity_id=str(rev.id),
                    action="archived_cold_storage",
                    after={"provider": "cold_storage"},
                    metadata={"module": "aerodoc_hybrid_dms", "job": "retention_runner"},
                )
            archived += 1
        db.commit()
        return archived
    finally:
        db.close()


if __name__ == "__main__":
    count = run_retention_cycle()
    print(f"AeroDoc retention runner archived {count} revisions")
