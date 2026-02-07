from __future__ import annotations

import json
from datetime import date, datetime

from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.quality import enums as quality_enums
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import schemas as quality_schemas
import importlib


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


def test_close_audit_requires_closed_findings(db_session):
    amo = account_models.AMO(
        amo_code="AMO-AUDIT",
        name="Audit AMO",
        login_slug="audit",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-200",
        title="Audit 200",
        status=quality_models.QMSAuditStatus.IN_PROGRESS,
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="Open finding",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
    )
    db_session.add(finding)
    db_session.commit()

    payload = quality_schemas.QMSAuditUpdate(status=quality_models.QMSAuditStatus.CLOSED)

    response = quality_router.update_audit(
        audit_id=audit.id,
        payload=payload,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["error"] == "missing_requirements"
    assert body["detail"][0]["field"] == "findings"


def test_close_finding_requires_evidence_and_verification(db_session):
    amo = account_models.AMO(
        amo_code="AMO-FINDING",
        name="Finding AMO",
        login_slug="finding",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-201",
        title="Audit 201",
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="Missing evidence",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
    )
    db_session.add(finding)
    db_session.commit()

    response = quality_router.close_finding(
        finding_id=finding.id,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["error"] == "missing_requirements"
    fields = {item["field"] for item in body["detail"]}
    assert {"objective_evidence", "verified_at"}.issubset(fields)


def test_close_finding_with_requirements_logs_transition(db_session):
    amo = account_models.AMO(
        amo_code="AMO-FIND-OK",
        name="Finding AMO OK",
        login_slug="finding-ok",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-202",
        title="Audit 202",
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="Evidence ok",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        objective_evidence="Photos attached",
        verified_at=datetime.utcnow(),
        verified_by_user_id=user.id,
    )
    db_session.add(finding)
    db_session.commit()

    result = quality_router.close_finding(
        finding_id=finding.id,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    assert result.closed_at is not None
    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "qms_finding", audit_models.AuditEvent.action == "transition")
        .first()
    )
    assert event is not None


def test_close_cap_requires_actions_evidence_and_verification(db_session):
    amo = account_models.AMO(
        amo_code="AMO-CAP",
        name="CAP AMO",
        login_slug="cap",
    )
    db_session.add(amo)
    db_session.commit()
    user = _create_user(db_session, amo_id=amo.id)

    audit = quality_models.QMSAudit(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref="AUD-203",
        title="Audit 203",
    )
    db_session.add(audit)
    db_session.commit()

    finding = quality_models.QMSAuditFinding(
        audit_id=audit.id,
        description="CAP finding",
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        objective_evidence="Evidence",
        verified_at=datetime.utcnow(),
        verified_by_user_id=user.id,
    )
    db_session.add(finding)
    db_session.commit()

    cap = quality_models.QMSCorrectiveAction(
        finding_id=finding.id,
    )
    db_session.add(cap)
    db_session.commit()

    payload = quality_schemas.QMSCAPUpsert(status=quality_enums.QMSCAPStatus.CLOSED)
    response = quality_router.upsert_cap(
        finding_id=finding.id,
        payload=payload,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["error"] == "missing_requirements"

    payload_ok = quality_schemas.QMSCAPUpsert(
        status=quality_enums.QMSCAPStatus.CLOSED,
        containment_action="Immediate action",
        corrective_action="Long-term fix",
        evidence_ref="cap-evidence.pdf",
        verified_at=datetime.utcnow(),
        verified_by_user_id=user.id,
    )
    result = quality_router.upsert_cap(
        finding_id=finding.id,
        payload=payload_ok,
        request=_make_request(),
        db=db_session,
        current_user=user,
    )

    assert result.status == quality_enums.QMSCAPStatus.CLOSED
