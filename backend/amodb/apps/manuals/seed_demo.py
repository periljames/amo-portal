from __future__ import annotations

from amodb.database import WriteSessionLocal
from amodb.apps.accounts.models import AMO
from amodb.apps.manuals import models


def seed_demo_manual() -> None:
    db = WriteSessionLocal()
    try:
        amo = db.query(AMO).filter(AMO.login_slug == "demo").first()
        if not amo:
            return
        tenant = db.query(models.Tenant).filter(models.Tenant.amo_id == amo.id).first()
        if not tenant:
            tenant = models.Tenant(amo_id=amo.id, slug=amo.login_slug, name=amo.name, settings_json={"ack_due_days": 10})
            db.add(tenant)
            db.flush()
        manual = db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id, models.Manual.code == "MTM-DEMO").first()
        if manual:
            db.commit()
            return
        manual = models.Manual(tenant_id=tenant.id, code="MTM-DEMO", title="Maintenance Training Manual Demo", manual_type="MTM", owner_role="Library")
        db.add(manual)
        db.flush()
        rev = models.ManualRevision(manual_id=manual.id, rev_number="0", issue_number="0", notes="Initial seeded draft")
        db.add(rev)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_manual()
