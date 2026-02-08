from __future__ import annotations

import io
import anyio
import importlib
import zipfile

from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.exports import evidence_pack as evidence_service
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import schemas as quality_schemas
from amodb.apps.quality import service as quality_service


quality_router = importlib.import_module("amodb.apps.quality.router")


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 1234),
        }
    )


def _create_user(db_session, *, amo_id: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email="qa@example.com",
        staff_code="QA1",
        first_name="QA",
        last_name="User",
        full_name="QA User",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
        is_amo_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_car_evidence_pack_contains_pdf_and_timeline(db_session, monkeypatch, tmp_path):
    amo = account_models.AMO(
        amo_code="AMO-CAR",
        name="CAR AMO",
        login_slug="car",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    car = quality_service.create_car(
        db_session,
        program=quality_models.CARProgram.QUALITY,
        title="Test CAR",
        summary="Summary",
        priority=quality_models.CARPriority.MEDIUM,
        requested_by_user_id=user.id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=None,
    )
    db_session.commit()

    pdf_path = tmp_path / "car.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy")

    monkeypatch.setattr(quality_service, "generate_car_form_pdf", lambda *_args, **_kwargs: pdf_path)

    response = evidence_service.build_evidence_pack(
        "qms_car",
        car.id,
        db_session,
        actor_user_id=user.id,
        correlation_id="test",
        amo_id=user.amo_id,
    )

    async def _collect() -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    body = anyio.run(_collect)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        assert "timeline.json" in names
        assert "car.pdf" in names

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(
            audit_models.AuditEvent.entity_type == "qms_car",
            audit_models.AuditEvent.action == "export_evidence_pack",
        )
        .first()
    )
    assert event is not None


def test_audit_evidence_pack_contains_summary_and_findings(db_session):
    amo = account_models.AMO(
        amo_code="AMO-AUD",
        name="Audit AMO",
        login_slug="audit",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit_payload = quality_schemas.QMSAuditCreate(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-1",
        title="Audit 1",
    )
    audit = quality_router.create_audit(
        payload=audit_payload,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    finding_payload = quality_schemas.QMSFindingCreate(
        description="Test finding",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
    )
    quality_router.add_finding(
        audit_id=audit.id,
        payload=finding_payload,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    response = evidence_service.build_evidence_pack(
        "qms_audit",
        audit.id,
        db_session,
        actor_user_id=user.id,
        correlation_id="test",
        amo_id=user.amo_id,
    )

    async def _collect() -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    body = anyio.run(_collect)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        assert "summary.json" in names
        assert "linked/findings.json" in names
        assert "timeline.json" in names

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(
            audit_models.AuditEvent.entity_type == "qms_audit",
            audit_models.AuditEvent.action == "export_evidence_pack",
        )
        .first()
    )
    assert event is not None
