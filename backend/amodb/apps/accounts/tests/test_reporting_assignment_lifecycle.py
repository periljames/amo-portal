from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.accounts import assignment_integrity
from amodb.apps.accounts import reporting_lifecycle_schemas as lifecycle_schemas
from amodb.apps.accounts import router_reporting_lines as reporting


def test_effective_period_overlap_is_inclusive() -> None:
    assert assignment_integrity.periods_overlap(
        date(2026, 8, 1),
        date(2026, 8, 5),
        date(2026, 8, 5),
        date(2026, 8, 10),
    ) is True
    assert assignment_integrity.periods_overlap(
        date(2026, 8, 1),
        date(2026, 8, 4),
        date(2026, 8, 5),
        None,
    ) is False
    assert assignment_integrity.periods_overlap(
        date(2026, 8, 1),
        None,
        date(2030, 1, 1),
        None,
    ) is True


def test_functional_quality_and_safety_roles_do_not_receive_tenant_wide_scope() -> None:
    quality = SimpleNamespace(
        is_superuser=False,
        is_amo_admin=False,
        role="QUALITY_MANAGER",
    )
    safety = SimpleNamespace(
        is_superuser=False,
        is_amo_admin=False,
        role="SAFETY_MANAGER",
    )
    tenant_admin = SimpleNamespace(
        is_superuser=False,
        is_amo_admin=True,
        role="QUALITY_MANAGER",
    )
    assert reporting._is_admin_actor(quality) is False
    assert reporting._is_admin_actor(safety) is False
    assert reporting._is_admin_actor(tenant_admin) is True


def test_transfer_requires_documented_matrix_reporting_reason() -> None:
    with pytest.raises(ValidationError):
        lifecycle_schemas.ReportingAssignmentTransfer(
            target_position_id="position-2",
            effective_from=date(2026, 8, 6),
            matrix_reporting=True,
            matrix_reason="",
            reason="Department transfer",
        )


def test_assignment_lifecycle_payload_preserves_decimal_fte() -> None:
    payload = lifecycle_schemas.ReportingAssignmentTransfer(
        target_position_id="position-2",
        effective_from=date(2026, 8, 6),
        fte_percent="33.33",
        reason="Temporary secondment",
    )
    assert str(payload.fte_percent) == "33.33"


def test_active_status_contract_covers_acting_and_approved_assignments() -> None:
    assert assignment_integrity.ACTIVE_STATUSES == {"ACTIVE", "ACTING", "APPROVED"}
    assert reporting.ACTIVE_ASSIGNMENT_STATUSES == {"ACTIVE", "ACTING", "APPROVED"}
