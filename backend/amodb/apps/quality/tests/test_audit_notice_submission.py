from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.notifications import models as notification_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality.audit_notice_models import (
    QualityAuditNotice,
    QualityAuditNoticeArtifact,
    QualityAuditNoticeEvent,
    QualityAuditNoticePolicy,
)
from amodb.apps.quality.audit_notice_router import (
    NoticeSubmit,
    _notice_email_correlation,
    submit_and_deliver_audit_notice,
)
from amodb.apps.quality.audit_occurrence_completion_models import QualityAuditMeeting
from amodb.apps.quality.tenant_security import TenantContext


def test_authorized_quality_officer_submits_signed_pdf_as_email_attachment(db_session, tmp_path, monkeypatch) -> None:
    Base.metadata.create_all(
        bind=db_session.get_bind(),
        tables=[
            QualityAuditNoticePolicy.__table__,
            QualityAuditNotice.__table__,
            QualityAuditNoticeArtifact.__table__,
            QualityAuditNoticeEvent.__table__,
            QualityAuditMeeting.__table__,
        ],
    )
    monkeypatch.setenv("AMO_STORAGE_BACKEND", "local")
    monkeypatch.setenv("AMO_STORAGE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path / "cache"))

    amo = account_models.AMO(
        amo_code="AMO-NOTICE",
        login_slug="amo-notice",
        name="Notice Test AMO",
        contact_email="quality@example.test",
        time_zone="Africa/Nairobi",
    )
    db_session.add(amo)
    db_session.flush()
    officer = account_models.User(
        amo_id=amo.id,
        email="officer@example.test",
        staff_code="QO-001",
        first_name="Quality",
        last_name="Officer",
        full_name="Quality Officer",
        position_title="Quality Officer",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_OFFICER,
        is_active=True,
    )
    db_session.add(officer)
    db_session.flush()
    audit = quality_models.QMSAudit(
        amo_id=amo.id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="QAR/AC/26/001",
        reference_family="QAR",
        unit_code="AC",
        ref_year=26,
        ref_sequence=1,
        title="Hangar quality system audit",
        scope="Aircraft maintenance quality system",
        criteria="Approved AMO procedures",
        auditee="Base Maintenance Manager",
        auditee_email="auditee@example.test",
        notify_auditors=False,
        notify_auditees=True,
        planned_start=date(2026, 9, 20),
        planned_end=date(2026, 9, 20),
        created_by_user_id=officer.id,
    )
    db_session.add(audit)
    db_session.flush()
    db_session.add_all([
        QualityAuditMeeting(
            amo_id=amo.id,
            audit_id=audit.id,
            meeting_type="OPENING",
            scheduled_start=datetime(2026, 9, 20, 5, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc),
            location="Briefing room",
            status="PLANNED",
            created_by_user_id=officer.id,
        ),
        QualityAuditMeeting(
            amo_id=amo.id,
            audit_id=audit.id,
            meeting_type="CLOSING",
            scheduled_start=datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc),
            location="Briefing room",
            status="PLANNED",
            created_by_user_id=officer.id,
        ),
    ])
    notice = QualityAuditNotice(
        amo_id=amo.id,
        audit_id=audit.id,
        revision_no=1,
        status="DRAFT",
        required_notice_days=14,
        notice_date=date(2026, 9, 1),
        subject="Audit Notice - QAR/AC/26/001 - Hangar quality system audit",
        body="Controlled notice",
        audit_snapshot={},
        recipient_snapshot=[],
        created_by_user_id=officer.id,
    )
    db_session.add(notice)
    db_session.commit()

    sends: list[dict] = []

    def fake_send_email(*_args, **kwargs):
        sends.append(kwargs)
        return SimpleNamespace(
            status=notification_models.EmailStatus.SENT,
            provider_message_id="email-notice-1",
            error=None,
        )

    monkeypatch.setattr("amodb.apps.quality.audit_notice_router.notification_service.send_email", fake_send_email)
    result = submit_and_deliver_audit_notice(
        audit_id=audit.id,
        notice_id=notice.id,
        payload=NoticeSubmit(reason="Notice preview verified by the issuing officer."),
        ctx=TenantContext(
            amo_code=amo.amo_code,
            amo_id=amo.id,
            user_id=officer.id,
            is_superuser=False,
        ),
        db=db_session,
    )

    assert result["delivery_complete"] is True
    assert result["notice"]["status"] == "DELIVERED"
    assert result["notice"]["artifact"]["source_type"] == "GENERATED"
    assert result["notice"]["artifact"]["signed_by_name"] == "Quality Officer"
    assert len(sends) == 1
    assert sends[0]["recipient"] == "auditee@example.test"
    assert sends[0]["attachments"][0]["content"].startswith(b"%PDF-")
    assert len(sends[0]["correlation_id"]) <= 64
    assert sends[0]["correlation_id"] == _notice_email_correlation(notice.id, "auditee@example.test")
    events = [row.event_type for row in db_session.query(QualityAuditNoticeEvent).order_by(QualityAuditNoticeEvent.created_at).all()]
    assert events == ["SUBMITTED", "APPROVED", "GENERATED", "DELIVERED"]
