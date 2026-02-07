from __future__ import annotations

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.workflow import apply_transition, TransitionError


def _create_amo(db_session) -> account_models.AMO:
    amo = account_models.AMO(
        amo_code="AMO-WF",
        name="Workflow AMO",
        login_slug="wf",
    )
    db_session.add(amo)
    db_session.commit()
    return amo


def test_apply_transition_allows_document_publish(db_session):
    amo = _create_amo(db_session)

    apply_transition(
        db_session,
        actor_user_id=None,
        entity_type="qms_document",
        entity_id="doc-1",
        from_state="DRAFT",
        to_state="ACTIVE",
        before_obj={"status": "DRAFT", "amo_id": amo.id},
        after_obj={
            "status": "ACTIVE",
            "approved_by_authority": True,
            "authority_ref": "CAA-REF",
            "amo_id": amo.id,
        },
        critical=True,
    )

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "qms_document", audit_models.AuditEvent.action == "transition")
        .first()
    )
    assert event is not None


def test_apply_transition_rejects_missing_finding_requirements(db_session):
    amo = _create_amo(db_session)

    with pytest.raises(TransitionError) as excinfo:
        apply_transition(
            db_session,
            actor_user_id=None,
            entity_type="qms_finding",
            entity_id="finding-1",
            from_state="OPEN",
            to_state="CLOSED",
            before_obj={"status": "OPEN", "amo_id": amo.id},
            after_obj={
                "status": "CLOSED",
                "objective_evidence": None,
                "verified_at": None,
                "amo_id": amo.id,
            },
            critical=True,
        )

    assert excinfo.value.code == "missing_requirements"
    assert {item["field"] for item in excinfo.value.detail} == {"objective_evidence", "verified_at"}


def test_apply_transition_rejects_invalid_transition(db_session):
    amo = _create_amo(db_session)

    with pytest.raises(TransitionError) as excinfo:
        apply_transition(
            db_session,
            actor_user_id=None,
            entity_type="qms_finding",
            entity_id="finding-2",
            from_state="CLOSED",
            to_state="OPEN",
            before_obj={"status": "CLOSED", "amo_id": amo.id},
            after_obj={"status": "OPEN", "amo_id": amo.id},
            critical=True,
        )

    assert excinfo.value.code == "invalid_transition"
