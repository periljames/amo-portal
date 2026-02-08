from __future__ import annotations

from amodb.apps.audit import services as audit_services
from amodb.apps.accounts import models as account_models


def test_log_event_writes_record(db_session):
    amo = account_models.AMO(
        amo_code="AMO-AUDIT",
        name="Audit AMO",
        login_slug="audit",
    )
    db_session.add(amo)
    db_session.commit()

    event = audit_services.log_event(
        db_session,
        amo_id=amo.id,
        actor_user_id=None,
        entity_type="qms_document",
        entity_id="doc-1",
        action="create",
        after={"status": "DRAFT"},
        metadata={"module": "quality"},
    )

    db_session.commit()
    assert event is not None
    assert event.entity_type == "qms_document"
