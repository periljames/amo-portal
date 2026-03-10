from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.compliance.ledger import write_ledger_event
from amodb.apps.doc_control.state_machine import (
    assert_doc_access_allowed,
    transition_revision_package,
)
from amodb.apps.quality.transitions import transition_car
from amodb.apps.training.gates import ensure_revision_training_gate_satisfied
from amodb.security import require_capability


class _Result:
    def __init__(self, value=0):
        self._value = value

    def scalar(self):
        return self._value

    def first(self):
        return None


class _DB:
    def __init__(self, *, fail_execute=False, capability_grants: set[tuple[str, str, str]] | None = None, unresolved=0):
        self.fail_execute = fail_execute
        self.capability_grants = capability_grants or set()
        self.unresolved = unresolved

    def execute(self, query, params=None):
        if self.fail_execute:
            raise RuntimeError("db failure")
        sql = str(query)
        params = params or {}

        if "FROM auth_user_role_assignments" in sql:
            key = (str(params.get("amo_id")), str(params.get("user_id")), str(params.get("capability_code")))
            return SimpleNamespace(fetchall=lambda: ([1] if key in self.capability_grants else []))

        if "COUNT(*)" in sql and "training_requirements" in sql:
            return _Result(self.unresolved)

        return _Result(0)

    def add(self, _obj):
        return None


def test_tenant_isolation_cross_tenant_access_denied() -> None:
    dep = require_capability("doc_control.revision.publish")
    user = SimpleNamespace(id="U1", amo_id="A2", is_superuser=False, is_amo_admin=False, role="TECHNICIAN")
    db = _DB(capability_grants={("A1", "U1", "doc_control.revision.publish")})
    with pytest.raises(HTTPException) as exc:
        dep(current_user=user, db=db)
    assert exc.value.status_code == 403


def test_capability_authz_required_for_doc_mutations() -> None:
    dep = require_capability("doc_control.document.create")
    user = SimpleNamespace(id="U9", amo_id="A1", is_superuser=False, is_amo_admin=False, role="TECHNICIAN")
    db = _DB(capability_grants=set())
    with pytest.raises(HTTPException):
        dep(current_user=user, db=db)


def test_invalid_transition_rejected_for_revision_workflow() -> None:
    package = SimpleNamespace(
        package_id="PKG-REV-1",
        internal_approval_status="Draft",
        requires_training=False,
        training_gate_policy="NONE",
    )
    with pytest.raises(HTTPException) as exc:
        transition_revision_package(
            _DB(),
            amo_id="A1",
            actor_user_id="U1",
            package=package,
            target_status="Published",
            evidence={"effective_date": "2026-01-01", "transmittal_notice": "N-1"},
        )
    assert exc.value.status_code == 409


def test_evidence_required_transition_rejected_without_payload() -> None:
    car = SimpleNamespace(id="CAR1", status="IN_PROGRESS", finding_id=None, evidence_ref=None)
    with pytest.raises(HTTPException) as exc:
        transition_car(
            _DB(),
            amo_id="A1",
            actor_user_id="U1",
            car=car,
            target_status="PENDING_VERIFICATION",
            evidence_ref=None,
        )
    assert exc.value.status_code == 400


def test_ledger_fail_closed_blocks_critical_transition() -> None:
    with pytest.raises(RuntimeError):
        write_ledger_event(
            _DB(fail_execute=True),
            amo_id="A1",
            entity_type="doc_control.revision_package",
            entity_id="PKG1",
            action="transition:Approved->Published",
            actor_user_id="U1",
            payload={"before": "Approved", "after": "Published"},
            critical=True,
            fail_closed=True,
        )


def test_training_gate_blocks_release_and_finding_closure() -> None:
    package = SimpleNamespace(package_id="PKG-1", requires_training=True, training_gate_policy="ALL_ASSIGNEES")
    with pytest.raises(HTTPException) as exc:
        ensure_revision_training_gate_satisfied(_DB(unresolved=1), amo_id="A1", package=package)
    assert exc.value.status_code == 409


def test_restricted_and_obsolete_access_control_enforced() -> None:
    obsolete_doc = SimpleNamespace(status="Superseded", restricted_flag=False)
    restricted_doc = SimpleNamespace(status="Active", restricted_flag=True)

    with pytest.raises(HTTPException) as exc1:
        assert_doc_access_allowed(doc=obsolete_doc, can_view_restricted=True)
    assert exc1.value.status_code == 403

    with pytest.raises(HTTPException) as exc2:
        assert_doc_access_allowed(doc=restricted_doc, can_view_restricted=False)
    assert exc2.value.status_code == 403
