from __future__ import annotations

import pytest

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


def test_log_event_does_not_rollback_outer_transaction_for_non_critical_errors(db_session, monkeypatch):
    amo = account_models.AMO(
        amo_code="AMO-NONCRIT",
        name="Audit Non Critical",
        login_slug="audit-noncrit",
    )
    db_session.add(amo)
    db_session.commit()

    asset = account_models.AMOAsset(
        amo_id=amo.id,
        kind=account_models.AMOAssetKind.OTHER,
        original_filename="asset.txt",
        storage_path="/tmp/asset.txt",
    )
    db_session.add(asset)

    def _raise_create(*args, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(audit_services, "create_audit_event", _raise_create)

    event = audit_services.log_event(
        db_session,
        amo_id=amo.id,
        actor_user_id=None,
        entity_type="qms_document",
        entity_id="doc-2",
        action="update",
        critical=False,
    )

    assert event is None
    db_session.commit()
    assert db_session.get(account_models.AMOAsset, asset.id) is not None


def test_log_event_raises_for_critical_publish_failures(db_session, monkeypatch):
    amo = account_models.AMO(
        amo_code="AMO-CRIT",
        name="Audit Critical",
        login_slug="audit-crit",
    )
    db_session.add(amo)
    db_session.commit()

    def _raise_publish(*args, **kwargs):
        raise RuntimeError("publish failed")

    monkeypatch.setattr(audit_services, "publish_event", _raise_publish)

    with pytest.raises(RuntimeError, match="publish failed"):
        audit_services.log_event(
            db_session,
            amo_id=amo.id,
            actor_user_id=None,
            entity_type="qms_document",
            entity_id="doc-3",
            action="close",
            critical=True,
        )
