from datetime import date, datetime, timedelta

from amodb.database import WriteSessionLocal
from amodb.apps.doc_control import models
from amodb.apps.accounts.models import AMO, User


def run():
    db = WriteSessionLocal()
    try:
        tenant = db.query(AMO).first()
        user = db.query(User).first()
        if not tenant:
            return
        tenant_id = tenant.id
        if db.query(models.ControlledDocument).filter_by(tenant_id=tenant_id, doc_id="MAN-001").first():
            return

        db.add(models.DocControlSettings(tenant_id=tenant_id))
        doc = models.ControlledDocument(
            tenant_id=tenant_id,
            doc_id="MAN-001",
            title="Maintenance Organization Exposition",
            doc_type="Manual",
            owner_department="Quality",
            issue_no=1,
            revision_no=1,
            version="1.1",
            effective_date=date.today(),
            status="Active",
            current_asset_id="asset-man-001-r1.pdf",
            physical_locations=[{"type": "library", "location_text": "Main library", "restricted_bool": False}],
            next_review_due=date.today() + timedelta(days=730),
        )
        db.add(doc)
        db.add(models.Draft(tenant_id=tenant_id, doc_id="MAN-001", asset_id="draft-man-001.pdf", status="Review"))
        rev = models.RevisionPackage(
            tenant_id=tenant_id,
            doc_id="MAN-001",
            revision_no=2,
            reference_serial_no="RP-001",
            change_summary="Updated chapter 1",
            transmittal_notice="Please replace pages.",
            filing_instructions="File in chapter 1",
            replacement_pages=[{"page_no": "1-1", "asset_id": "page-1-1.pdf"}],
            effective_date=date.today(),
            internal_approval_status="Approved",
            published_at=datetime.utcnow(),
        )
        db.add(rev)
        tr = models.TemporaryRevision(
            tenant_id=tenant_id,
            doc_id="MAN-001",
            tr_no="TR-001",
            effective_date=date.today(),
            expiry_date=date.today() + timedelta(days=90),
            reason="Urgent correction",
            filing_instructions="Insert after page 2-1",
            updated_lep_asset_id="lep-tr-001.pdf",
            status="InForce",
        )
        db.add(tr)
        ev = models.DistributionEvent(
            tenant_id=tenant_id,
            doc_id="MAN-001",
            source_type="RevisionPackage",
            source_id="seed-revision-package",
            method="Portal",
            sent_at=datetime.utcnow(),
            acknowledgement_required=True,
            status="Sent",
        )
        db.add(ev)
        db.flush()
        db.add(models.Acknowledgement(tenant_id=tenant_id, event_id=ev.event_id, recipient_user_id=(user.id if user else None), method="Form"))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
