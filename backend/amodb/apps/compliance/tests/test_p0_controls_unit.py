from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.compliance.ledger import write_ledger_event
from amodb.apps.doc_control import state_machine as doc_state
from amodb.apps.quality import transitions as car_transitions
from amodb.apps.training import gates
from amodb.security import require_capability


class _Result:
    def __init__(self, value=0):
        self._value = value

    def scalar(self):
        return self._value

    def first(self):
        return None


class _DB:
    def __init__(self, *, fail_execute=False, allowed=False, unresolved=0):
        self.fail_execute = fail_execute
        self.allowed = allowed
        self.unresolved = unresolved

    def execute(self, *args, **kwargs):
        if self.fail_execute:
            raise RuntimeError("db failure")
        sql = str(args[0])
        if "FROM auth_user_role_assignments" in sql:
            return SimpleNamespace(fetchall=lambda: ([1] if self.allowed else []))
        if "COUNT(*)" in sql and "training_requirements" in sql:
            return _Result(self.unresolved)
        return _Result(0)

    def add(self, _obj):
        return None


def test_require_capability_denies_without_capability():
    dep = require_capability("doc_control.revision.publish")
    user = SimpleNamespace(id="U1", amo_id="A1", is_superuser=False, is_amo_admin=False, role="TECHNICIAN")
    db = _DB(allowed=False)
    with pytest.raises(HTTPException) as exc:
        dep(current_user=user, db=db)
    assert exc.value.status_code == 403


def test_revision_transition_invalid_state_rejected():
    package = SimpleNamespace(package_id="PKG1", internal_approval_status="Draft", requires_training=False, training_gate_policy="NONE")
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        doc_state.transition_revision_package(
            db,
            amo_id="A1",
            actor_user_id="U1",
            package=package,
            target_status="Published",
            evidence={"effective_date": "2026-01-01", "transmittal_notice": "x"},
        )
    assert exc.value.status_code == 409


def test_car_transition_requires_evidence():
    car = SimpleNamespace(id="CAR1", status="OPEN", finding_id=None, evidence_ref=None)
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        car_transitions.transition_car(
            db,
            amo_id="A1",
            actor_user_id="U1",
            car=car,
            target_status="ACKNOWLEDGED",
            evidence_ref=None,
        )
    assert exc.value.status_code == 400


def test_ledger_fail_closed_raises_on_db_failure():
    db = _DB(fail_execute=True)
    with pytest.raises(RuntimeError):
        write_ledger_event(
            db,
            amo_id="A1",
            entity_type="doc_control.revision_package",
            entity_id="PKG1",
            action="transition",
            actor_user_id="U1",
            payload={"x": 1},
            fail_closed=True,
        )


def test_training_gate_blocks_when_unresolved_requirements():
    db = _DB(unresolved=2)
    package = SimpleNamespace(package_id="PKG1", requires_training=True, training_gate_policy="ALL_ASSIGNEES")
    with pytest.raises(HTTPException) as exc:
        gates.ensure_revision_training_gate_satisfied(db, amo_id="A1", package=package)
    assert exc.value.status_code == 409


def test_obsolete_access_blocked():
    doc = SimpleNamespace(status="Superseded", restricted_flag=False)
    with pytest.raises(HTTPException) as exc:
        doc_state.assert_doc_access_allowed(doc=doc, can_view_restricted=True)
    assert exc.value.status_code == 403
