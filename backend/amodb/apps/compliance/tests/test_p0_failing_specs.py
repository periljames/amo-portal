from __future__ import annotations

import pytest


@pytest.mark.p0_spec
def test_tenant_isolation_cross_tenant_access_denied() -> None:
    pytest.fail("P0 spec failing: doc_control and quality mutation routes not fully enforced by amo_id+capability gate")


@pytest.mark.p0_spec
def test_capability_authz_required_for_doc_mutations() -> None:
    pytest.fail("P0 spec failing: routes still use get_current_active_user without require_capability on all mutation endpoints")


@pytest.mark.p0_spec
def test_invalid_transition_rejected_for_revision_workflow() -> None:
    pytest.fail("P0 spec failing: revision transition map not yet wired to all revision endpoints")


@pytest.mark.p0_spec
def test_evidence_required_transition_rejected_without_payload() -> None:
    pytest.fail("P0 spec failing: evidence-required checks not yet enforced across CAR/CAPA/effectiveness transitions")


@pytest.mark.p0_spec
def test_ledger_fail_closed_blocks_critical_transition() -> None:
    pytest.fail("P0 spec failing: critical transition routes are not yet transactionally coupled to compliance_event_ledger writer")


@pytest.mark.p0_spec
def test_training_gate_blocks_release_and_finding_closure() -> None:
    pytest.fail("P0 spec failing: training gate validator not yet wired into release/closure transitions")


@pytest.mark.p0_spec
def test_restricted_and_obsolete_access_control_enforced() -> None:
    pytest.fail("P0 spec failing: superseded/archived operational lockout and restricted-justification policy not fully wired")
