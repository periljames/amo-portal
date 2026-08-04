import pytest
from pydantic import ValidationError

from amodb.apps.integrations.migration_schemas import (
    MigrationBatchCreate,
    MigrationReconciliationDecision,
    MigrationStageRequest,
)


def test_batch_requires_target_identity():
    with pytest.raises(ValidationError):
        MigrationBatchCreate(name="Pilot batch")


def test_batch_accepts_5y_sls_registration_target():
    batch = MigrationBatchCreate(
        name="5Y-SLS pilot",
        target_registration="5Y-SLS",
    )
    assert batch.target_registration == "5Y-SLS"
    assert batch.source_type == "SPREADSHEET"


def test_stage_requires_at_least_one_row():
    with pytest.raises(ValidationError):
        MigrationStageRequest(rows=[])


def test_merge_resolution_requires_payload():
    with pytest.raises(ValidationError):
        MigrationReconciliationDecision(
            resolution="MERGE",
            resolution_notes="Merge reviewed fields",
        )


def test_accept_source_does_not_require_merge_payload():
    decision = MigrationReconciliationDecision(
        resolution="ACCEPT_SOURCE",
        resolution_notes="Source evidence verified",
    )
    assert decision.merged_payload is None
