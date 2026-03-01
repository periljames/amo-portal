from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.jobs import aerodoc_retention_runner


def test_retention_runner_uses_valid_amo_id_for_audit(monkeypatch, db_session):
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()

    owner = account_models.User(
        amo_id=amo.id,
        email=f"owner-{uuid4()}@example.com",
        staff_code=f"OWN-{uuid4().hex[:6]}",
        first_name="Owner",
        last_name="User",
        full_name="Owner User",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()

    doc = quality_models.QMSDocument(
        domain=quality_models.QMSDomain.AMO,
        doc_type=quality_models.QMSDocType.MANUAL,
        doc_code=f"DOC-{uuid4().hex[:6]}",
        title="Retention Doc",
        retention_category=quality_models.QMSRetentionCategory.MAINT_RECORD_5Y,
        owner_user_id=owner.id,
    )
    db_session.add(doc)
    db_session.flush()

    rev = quality_models.QMSDocumentRevision(
        document_id=doc.id,
        issue_no=1,
        rev_no=0,
        created_by_user_id=owner.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=365 * 6),
        primary_storage_provider="s3",
    )
    db_session.add(rev)
    db_session.commit()

    captured = []

    def _fake_log_event(db, **kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(aerodoc_retention_runner, "WriteSessionLocal", lambda: db_session)
    monkeypatch.setattr(aerodoc_retention_runner.audit_services, "log_event", _fake_log_event)

    count = aerodoc_retention_runner.run_retention_cycle()

    assert count == 1
    updated = db_session.query(quality_models.QMSDocumentRevision).filter_by(id=rev.id).first()
    assert updated is not None
    assert updated.primary_storage_provider == "cold_storage"
    assert captured and captured[0]["amo_id"] == amo.id
