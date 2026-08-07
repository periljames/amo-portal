import pytest

from amodb.apps.aircraft_architecture.import_staging import services


def test_batch_state_machine_is_sequential():
    services.require_batch_transition("STAGED", "VALIDATED")
    services.require_batch_transition("VALIDATED", "RECONCILED")
    services.require_batch_transition("RECONCILED", "APPROVED")
    with pytest.raises(ValueError, match="invalid import batch transition"):
        services.require_batch_transition("STAGED", "APPROVED")


def test_batch_approval_requires_dataset_and_resolved_errors():
    services.approval_preconditions(dataset_count=1, open_error_count=0)
    with pytest.raises(ValueError, match="dataset"):
        services.approval_preconditions(dataset_count=0, open_error_count=0)
    with pytest.raises(ValueError, match="open ERROR"):
        services.approval_preconditions(dataset_count=1, open_error_count=2)
