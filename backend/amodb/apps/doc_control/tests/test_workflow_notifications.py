from types import SimpleNamespace

from amodb.apps.accounts import models as accounts
from amodb.apps.doc_control import workflow_notifications as service
from amodb.apps.realtime.models import PortalNotification, RealtimeOutbox


def test_upload_notifications_are_scoped_deduplicated_and_transactional(db_session, monkeypatch):
    amo = accounts.AMO(amo_code="DMS", name="DMS", login_slug="dms")
    other = accounts.AMO(amo_code="OTHER", name="Other", login_slug="other")
    db_session.add_all([amo, other])
    db_session.flush()
    users = []
    for name, role, tenant_id in [
        ("uploader", "QUALITY_OFFICER", amo.id),
        ("admin", "AMO_ADMIN", amo.id),
        ("reader", "AUDITOR", amo.id),
        ("restricted", "AMO_ADMIN", amo.id),
        ("outside", "AMO_ADMIN", other.id),
    ]:
        user = accounts.User(
            amo_id=tenant_id, staff_code=name, email=f"{name}@example.com",
            first_name=name, last_name="Test", full_name=name,
            role=role, hashed_password="x", is_active=True, is_system_account=False,
        )
        db_session.add(user)
        users.append(user)
    db_session.commit()
    creator, admin, reader, restricted, outsider = users
    monkeypatch.setattr(service, "get_profile", lambda *args: None)
    monkeypatch.setattr(service, "can_read_manual", lambda user, profile: user.id != restricted.id)
    tenant = SimpleNamespace(amo_id=amo.id, slug="dms")
    manual = SimpleNamespace(id="manual-1", code="CHK-1", title="Audit checklist")
    workflow = SimpleNamespace(id="workflow-1", tenant_id=amo.id, manual_id=manual.id,
                               revision_id="revision-1", state="DRAFT", version=1,
                               created_by_user_id=creator.id)
    service.notify_workflow_progress(db_session, tenant=tenant, manual=manual, workflow=workflow)
    service.notify_workflow_progress(db_session, tenant=tenant, manual=manual, workflow=workflow)
    rows = db_session.query(PortalNotification).all()
    assert {row.user_id for row in rows} == {creator.id, admin.id}
    assert len(rows) == 2
    assert all("workflow=workflow-1" in row.action_url for row in rows)
    assert db_session.query(RealtimeOutbox).count() == 2

    # A workflow change is a new notification, including progress for the uploader.
    workflow.state = "PUBLISHED"
    workflow.version = 2
    service.notify_workflow_progress(db_session, tenant=tenant, manual=manual, workflow=workflow)
    assert db_session.query(PortalNotification).filter_by(user_id=creator.id).count() == 2
    assert db_session.query(PortalNotification).filter_by(user_id=outsider.id).count() == 0
    assert db_session.query(PortalNotification).filter_by(user_id=reader.id).count() == 0
    db_session.rollback()
    assert db_session.query(PortalNotification).count() == 0
    assert db_session.query(RealtimeOutbox).count() == 0
