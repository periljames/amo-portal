from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

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
    _normalise_notice_schedule_snapshot,
    _normalise_recipient_snapshot,
    _notice_email_correlation,
    _require_latest_notice_revision,
    prepare_audit_notice_document,
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
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/maintenance/AMO-NOTICE/quality/audits/audit/notices/notice",
        "headers": [(b"origin", b"https://portal.example.test")],
        "scheme": "https",
        "server": ("api.example.test", 443),
        "query_string": b"",
    })
    context = TenantContext(
        amo_code=amo.amo_code,
        amo_id=amo.id,
        user_id=officer.id,
        is_superuser=False,
    )
    with pytest.raises(HTTPException) as preview_required:
        submit_and_deliver_audit_notice(
            audit_id=audit.id,
            notice_id=notice.id,
            request=request,
            payload=NoticeSubmit(reason="Attempted delivery before reviewing the final document."),
            ctx=context,
            db=db_session,
        )
    assert preview_required.value.status_code == 409
    assert preview_required.value.detail["code"] == "AUDIT_NOTICE_FINAL_PREVIEW_REQUIRED"
    assert sends == []

    opening = db_session.query(QualityAuditMeeting).filter(
        QualityAuditMeeting.audit_id == audit.id,
        QualityAuditMeeting.meeting_type == "OPENING",
    ).one()
    opening.status = "CANCELLED"
    db_session.commit()
    with pytest.raises(HTTPException) as cancelled_meeting:
        prepare_audit_notice_document(
            audit_id=audit.id,
            notice_id=notice.id,
            request=request,
            payload=NoticeSubmit(reason="Attempted generation with a cancelled opening meeting."),
            ctx=context,
            db=db_session,
        )
    assert cancelled_meeting.value.status_code == 409
    assert cancelled_meeting.value.detail["code"] == "AUDIT_NOTICE_MEETINGS_REQUIRED"
    opening.status = "PLANNED"
    db_session.commit()

    prepared = prepare_audit_notice_document(
        audit_id=audit.id,
        notice_id=notice.id,
        request=request,
        payload=NoticeSubmit(reason="Final signed notice prepared for controlled preview."),
        ctx=context,
        db=db_session,
    )
    assert prepared["status"] == "GENERATED"
    assert prepared["artifact"]["source_type"] == "GENERATED"

    # A generated notice is immutable. If the audit definition or meetings move,
    # the stored PDF must become historical and delivery must require a revision.
    original_title = audit.title
    original_audit_ref = audit.audit_ref
    original_external_auditees_json = audit.external_auditees_json
    original_opening_start = opening.scheduled_start
    original_opening_end = opening.scheduled_end
    audit.title = "Hangar quality system audit - deferred"
    audit.audit_ref = "QAR/AC/26/002"
    audit.external_auditees_json = json.dumps([{
        "first_name": "External",
        "last_name": "Process Owner",
        "email": "external@example.test",
        "phone_contact": None,
        "designation": "Process owner",
    }])
    opening.scheduled_start = opening.scheduled_start.replace(hour=7)
    opening.scheduled_end = opening.scheduled_end.replace(hour=8)
    db_session.commit()

    with pytest.raises(HTTPException) as stale_notice:
        submit_and_deliver_audit_notice(
            audit_id=audit.id,
            notice_id=notice.id,
            request=request,
            payload=NoticeSubmit(reason="Attempted delivery after audit arrangements changed."),
            ctx=context,
            db=db_session,
        )
    assert stale_notice.value.status_code == 409
    assert stale_notice.value.detail["code"] == "AUDIT_NOTICE_REVISION_REQUIRED"
    changed_labels = {item["label"] for item in stale_notice.value.detail["changes"]}
    assert "Audit title" in changed_labels
    assert "Audit reference" in changed_labels
    assert "Notice recipients" in changed_labels
    assert "Opening meeting" in changed_labels
    assert sends == []

    audit.title = original_title
    audit.audit_ref = original_audit_ref
    audit.external_auditees_json = original_external_auditees_json
    opening.scheduled_start = original_opening_start
    opening.scheduled_end = original_opening_end
    db_session.commit()

    result = submit_and_deliver_audit_notice(
        audit_id=audit.id,
        notice_id=notice.id,
        request=request,
        payload=NoticeSubmit(reason="Notice preview verified by the issuing officer."),
        ctx=context,
        db=db_session,
    )

    assert result["delivery_complete"] is True
    assert result["notice"]["status"] == "DELIVERED"
    assert result["notice"]["artifact"]["source_type"] == "GENERATED"
    assert result["notice"]["artifact"]["signed_by_name"] == "Quality Officer"
    assert len(sends) == 1
    assert sends[0]["recipient"] == "auditee@example.test"
    assert sends[0]["attachments"][0]["content"].startswith(b"%PDF-")
    assert hashlib.sha256(sends[0]["attachments"][0]["content"]).hexdigest() == result["notice"]["artifact"]["sha256"]
    assert sends[0]["context"]["action_url"].startswith("https://portal.example.test/maintenance/AMO-NOTICE/")
    assert f"noticeId={notice.id}" in sends[0]["context"]["action_url"]
    assert len(sends[0]["correlation_id"]) <= 64
    assert sends[0]["correlation_id"] == _notice_email_correlation(notice.id, "auditee@example.test")
    events = [row.event_type for row in db_session.query(QualityAuditNoticeEvent).order_by(QualityAuditNoticeEvent.created_at).all()]
    assert events == ["SUBMITTED", "APPROVED", "GENERATED", "DELIVERED"]

    next_notice = QualityAuditNotice(
        amo_id=amo.id,
        audit_id=audit.id,
        revision_no=2,
        status="DRAFT",
        required_notice_days=14,
        notice_date=date(2026, 9, 2),
        subject="Revised controlled notice",
        body="Controlled notice revision",
        audit_snapshot={"audit_ref": audit.audit_ref},
        recipient_snapshot=[],
        supersedes_notice_id=str(notice.id),
        created_by_user_id=officer.id,
    )
    db_session.add(next_notice)
    db_session.commit()
    with pytest.raises(HTTPException) as historical_revision:
        _require_latest_notice_revision(db_session, notice)
    assert historical_revision.value.status_code == 409
    assert historical_revision.value.detail["code"] == "AUDIT_NOTICE_NOT_LATEST"
    assert historical_revision.value.detail["latest_notice_revision"] == 2



def test_legacy_and_current_recipient_snapshots_compare_by_governed_routing() -> None:
    legacy = [{
        "role": "LEAD_AUDITOR",
        "user_id": "user-1",
        "name": "Quality Officer",
        "email": "QUALITY@example.test",
    }]
    current = [{
        "role": "lead_auditor",
        "user_id": "user-1",
        "email": "quality@example.test",
    }]

    assert _normalise_recipient_snapshot(legacy) == _normalise_recipient_snapshot(current)

    changed_email = [{
        "role": "LEAD_AUDITOR",
        "user_id": "user-1",
        "email": "new-quality@example.test",
    }]
    assert _normalise_recipient_snapshot(legacy) != _normalise_recipient_snapshot(changed_email)


    external_legacy = [{
        "role": "EXTERNAL_AUDITEE",
        "first_name": "External",
        "last_name": "Process Owner",
        "designation": "Process owner",
        "email": "external@example.test",
    }]
    external_resolved = [{
        **external_legacy[0],
        "name": "External Process Owner",
    }]
    assert _normalise_recipient_snapshot(external_legacy) == _normalise_recipient_snapshot(external_resolved)



def test_notice_schedule_snapshot_treats_implicit_default_times_as_effective_defaults() -> None:
    implicit = {
        "planned_start": "2026-09-30",
        "planned_end": "2026-09-30",
        "planned_start_time": None,
        "planned_end_time": None,
    }
    explicit = {
        "planned_start": "2026-09-30",
        "planned_end": "2026-09-30",
        "planned_start_time": "09:00",
        "planned_end_time": "17:00",
    }

    assert _normalise_notice_schedule_snapshot(implicit) == explicit
    assert _normalise_notice_schedule_snapshot(implicit) == _normalise_notice_schedule_snapshot(explicit)
