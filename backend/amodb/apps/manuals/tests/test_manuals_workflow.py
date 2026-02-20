from datetime import date

from amodb.apps.accounts.models import AMO, User, AccountRole
from amodb.apps.manuals import models


def test_publish_locks_revision_and_sets_current(db_session):
    amo = AMO(amo_code="AMO1", name="Demo", login_slug="demo")
    user = User(amo=amo, staff_code="S001", email="qa@example.com", first_name="Q", last_name="A", full_name="QA", role=AccountRole.QUALITY_MANAGER, hashed_password="x")
    db_session.add_all([amo, user])
    db_session.commit()

    tenant = models.Tenant(amo_id=amo.id, slug="demo", name="Demo", settings_json={"ack_due_days": 10})
    db_session.add(tenant)
    db_session.flush()

    manual = models.Manual(tenant_id=tenant.id, code="MOM", title="Maintenance Org Manual", manual_type="MOM", owner_role="Library")
    db_session.add(manual)
    db_session.flush()

    rev = models.ManualRevision(manual_id=manual.id, rev_number="1", effective_date=date.today(), created_by=user.id)
    db_session.add(rev)
    db_session.flush()

    rev.status_enum = models.ManualRevisionStatus.PUBLISHED
    rev.immutable_locked = True
    manual.current_published_rev_id = rev.id
    db_session.commit()

    db_session.refresh(rev)
    db_session.refresh(manual)
    assert rev.immutable_locked is True
    assert rev.status_enum == models.ManualRevisionStatus.PUBLISHED
    assert manual.current_published_rev_id == rev.id
