"""Execute the transaction with real ORM writes in the isolated test database."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from amodb.database import Base
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models
from amodb.apps.quality import audit_checklist_execution_router as execution
from amodb.apps.quality import audit_checklist_execution_models as state
from amodb.apps.quality.tenant_security import TenantContext


@pytest.fixture
def atomic_context(db_session, monkeypatch):
    Base.metadata.create_all(db_session.get_bind(), tables=[
        models.QualityAuditChecklistItem.__table__,
        state.QualityAuditChecklistExecutionGovernance.__table__,
        state.QualityAuditChecklistExecutionEvent.__table__,
        state.QualityAuditFieldworkMutationReceipt.__table__,
    ])
    amo = accounts.AMO(amo_code="ATOMIC", login_slug="atomic", name="Atomic test")
    db_session.add(amo)
    db_session.flush()
    user = accounts.User(amo_id=amo.id, email="auditor@example.test", staff_code="A1",
        first_name="Test", last_name="Auditor", full_name="Test Auditor", position_title="Auditor", hashed_password="test", is_active=True,
        role=accounts.AccountRole.QUALITY_OFFICER)
    db_session.add(user)
    db_session.flush()
    audit = models.QMSAudit(amo_id=amo.id, domain=models.QMSDomain.AMO,
        audit_ref="QAR/MO/26/TEST", title="Isolated test", lead_auditor_user_id=user.id,
        auditee_user_id=user.id)
    db_session.add(audit)
    db_session.flush()
    item = models.QualityAuditChecklistItem(amo_id=amo.id, audit_id=audit.id,
        checklist_ref="1.1", prompt="Test question")
    db_session.add(item)
    db_session.commit()
    ctx = TenantContext(amo_code="ATOMIC", amo_id=amo.id, user_id=user.id, is_superuser=False)
    monkeypatch.setattr(execution, "assert_quality_permission_any", lambda *a, **kw: None)
    monkeypatch.setattr(execution, "set_postgres_tenant_context", lambda *a, **kw: None)
    monkeypatch.setattr(execution, "_internal_fieldwork_viewer", lambda *a, **kw: (audit, user, execution.models))
    # Match the package export returned by the real actor resolver. Using the
    # implementation module conceals missing helpers on the composed router.
    from amodb.apps import quality as quality_package
    quality = quality_package.router
    monkeypatch.setattr(execution, "_internal_fieldwork_actor", lambda *a, **kw: (audit, user, quality))
    monkeypatch.setattr(execution, "_frozen_item_definition_map", lambda *a, **kw: {str(item.id): {
        "response_type": "YES_NO_NA", "response_options": [
            {"value": "YES", "label": "YES", "canonical_status": "COMPLIANT"},
            {"value": "NO", "label": "NO", "canonical_status": "NONCOMPLIANT"},
            {"value": "NA", "label": "N/A", "canonical_status": "NOT_APPLICABLE"},
        ],
    }})
    monkeypatch.setattr(execution, "_publish_persisted_event", lambda *a, **kw: None)
    return SimpleNamespace(db=db_session, ctx=ctx, audit=audit, item=item)


@pytest.mark.parametrize("level,severity", [("LEVEL_1", "CRITICAL"), ("LEVEL_2", "MAJOR"), ("LEVEL_3", "MINOR")])
def test_no_finding_and_car_commit_together(atomic_context, level, severity):
    c = atomic_context
    payload = execution.FieldworkFindingMutation(
        client_mutation_id=f"atomic-finding-{level}", device_id="atomic-device-test",
        device_sequence=1, client_timestamp=datetime.now(timezone.utc), base_version=0,
        canonical_response_status="NONCOMPLIANT", response_value="NO", severity=severity,
        level=level, description="Test nonconformity", objective_evidence="Synthetic test evidence",
        auditor_notes="Synthetic transaction test", reason="Test atomic answer and finding persistence")
    result = execution.create_atomic_fieldwork_finding(c.audit.id, c.item.id, payload, c.ctx, c.db)
    assert result["row"]["response_value"] == "NO"
    assert result["row"]["canonical_response_status"] == "NONCOMPLIANT"
    assert result["car_id"]
    c.db.expire_all()
    assert c.db.get(models.QualityAuditChecklistItem, c.item.id).finding_id
    assert c.db.query(models.CorrectiveActionRequest).count() == 1
    replay = execution.create_atomic_fieldwork_finding(c.audit.id, c.item.id, payload, c.ctx, c.db)
    assert replay["replayed"] is True
    assert c.db.query(models.QMSAuditFinding).count() == 1


@pytest.mark.parametrize("answer,canonical", [("YES", "COMPLIANT"), ("NO", "NONCOMPLIANT")])
def test_observation_keeps_an_approved_source_answer_without_a_car(atomic_context, answer, canonical):
    c = atomic_context
    payload = execution.FieldworkFindingMutation(
        client_mutation_id="observation-source-test", device_id="atomic-device-test", device_sequence=2,
        client_timestamp=datetime.now(timezone.utc), base_version=0,
        canonical_response_status=canonical, response_value=answer, severity="MINOR", level="LEVEL_4",
        description="Synthetic observation", auditor_notes="Synthetic source answer",
        reason="Record observation independently of source response")
    result = execution.create_atomic_fieldwork_finding(c.audit.id, c.item.id, payload, c.ctx, c.db)
    assert result["row"]["response_value"] == answer
    assert result["row"]["canonical_response_status"] == canonical
    assert result["finding"]["level"] == "LEVEL_4"
    assert result["car_id"] is None
    assert c.db.query(models.CorrectiveActionRequest).count() == 0


def test_invalid_answer_rolls_back_finding_car_and_answer(atomic_context):
    from fastapi import HTTPException
    c = atomic_context
    payload = execution.FieldworkFindingMutation(
        client_mutation_id="invalid-source-test", device_id="atomic-device-test", device_sequence=3,
        client_timestamp=datetime.now(timezone.utc), base_version=0,
        canonical_response_status="NONCOMPLIANT", response_value="YES", severity="MAJOR", level="LEVEL_2",
        description="Synthetic invalid response", auditor_notes="Synthetic transaction test",
        reason="Verify all transaction writes roll back together")
    with pytest.raises(HTTPException):
        execution.create_atomic_fieldwork_finding(c.audit.id, c.item.id, payload, c.ctx, c.db)
    assert c.db.query(models.QMSAuditFinding).count() == 0
    assert c.db.query(models.CorrectiveActionRequest).count() == 0
    assert c.db.query(state.QualityAuditFieldworkMutationReceipt).count() == 0
    assert c.db.get(models.QualityAuditChecklistItem, c.item.id).response_status == "PENDING"
