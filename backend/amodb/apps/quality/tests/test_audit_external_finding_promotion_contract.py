from __future__ import annotations

import inspect

from amodb.apps.quality import audit_external_finding_promotion_router as promotion_router
from amodb.apps.quality.audit_official_finding_service import create_official_finding_transaction
from amodb.apps.quality.enums import FindingLevel, QMSFindingSeverity


def test_official_finding_service_does_not_own_commit_or_publish_boundary():
    source = inspect.getsource(create_official_finding_transaction)
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "publish_event(" not in source


def test_shared_service_accepts_same_governed_classification_vocabulary():
    signature = inspect.signature(create_official_finding_transaction)
    assert "canonical_response_status" in signature.parameters
    assert "severity" in signature.parameters
    assert "level" in signature.parameters
    assert "correlation_id" in signature.parameters
    assert "source_metadata" in signature.parameters
    assert "expected_base_version" in signature.parameters


def test_promotion_route_is_quality_owned_and_uses_shared_transaction_source():
    source = inspect.getsource(promotion_router.promote_external_finding_draft)
    assert 'assert_quality_permission(db, ctx, "qms.audit.manage")' in source
    assert "create_official_finding_transaction(" in source
    assert 'event_type="PROMOTED"' in source
    assert "promoted_finding_id=result.finding.id" in source
    assert "db.commit()" in source
    assert "db.rollback()" in source


def test_promotion_route_never_writes_external_participant_into_employee_actor():
    source = inspect.getsource(promotion_router.promote_external_finding_draft)
    assert "actor_user_id=ctx.user_id" in source
    assert '"externalParticipantId": row.participant_id' in source
    assert "actor_user_id=row.participant_id" not in source


def test_official_classification_types_remain_existing_quality_enums():
    assert QMSFindingSeverity.MAJOR.value == "MAJOR"
    assert FindingLevel.LEVEL_2.value == "LEVEL_2"
