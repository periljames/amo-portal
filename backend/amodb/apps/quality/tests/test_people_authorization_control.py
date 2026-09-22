from __future__ import annotations

import inspect

from amodb.apps.accounts import access_control
from amodb.apps.quality import audit_assignment_guard, people_authorization_router, people_router, tenant_security
from amodb.apps.quality.people_models import QualityPrivilegeDecision
from amodb.apps.quality.people_authorization_models import (
    QualityAuthorizationCase,
    QualityAuthorizationCaseEvent,
    QualityAuthorizationReview,
    QualityControlledExemption,
)


def _routes(router):
    return {
        (str(route.path), method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def test_people_surface_has_one_governed_authorization_lifecycle() -> None:
    routes = _routes(people_router) | _routes(people_authorization_router)
    assert ("/people/authorization-control/cases", "POST") in routes
    assert ("/people/authorization-control/cases/{case_id}/submit", "POST") in routes
    assert ("/people/authorization-control/cases/{case_id}/decision", "POST") in routes
    assert ("/people/authorization-control/authorizations/{privilege_id}/lifecycle", "POST") in routes
    assert ("/people/authorization-control/authorizations/{privilege_id}/reviews", "POST") in routes
    assert not any("/people/privileges" in path for path, _method in routes)
    assert not any("qm-bypass" in path or path.endswith("/rank") for path, _method in routes)
    assert not any(method == "DELETE" for path, method in routes if path.startswith("/people/"))


def test_quality_officer_prepares_but_does_not_approve_authorizations() -> None:
    officer = tenant_security._QUALITY_ROLE_PERMISSIONS["QUALITY_OFFICER"]
    assert "qms.people.view" in officer
    assert "qms.authorization.prepare" in officer
    assert "qms.authorization.approve" not in officer
    assert "qms.authorization.review" not in officer
    assert "qms.authorization.exemption.approve" not in officer

    assert "qms.authorization.prepare" in access_control.QUALITY_OFFICER_CAPABILITIES
    assert "qms.authorization.approve" not in access_control.QUALITY_OFFICER_CAPABILITIES
    assert "qms.authorization.approve" in access_control.QUALITY_MANAGER_CAPABILITIES
    assert "qms.authorization.review" in access_control.QUALITY_MANAGER_CAPABILITIES
    assert "qms.authorization.exemption.approve" in access_control.QUALITY_MANAGER_CAPABILITIES


def test_accountable_executive_has_oversight_without_mutation_authority() -> None:
    executive = tenant_security._QUALITY_ROLE_PERMISSIONS["ACCOUNTABLE_EXECUTIVE"]
    assert "qms.people.view" in executive
    assert "qms.authorization.oversight" in executive
    assert "qms.authorization.prepare" not in executive
    assert "qms.authorization.approve" not in executive
    assert "qms.authorization.review" not in executive


def test_training_recurrence_is_not_created_by_authorization_control() -> None:
    source = inspect.getsource(people_authorization_router)
    assert "TrainingCourse(" not in source
    assert "frequency_months" not in source
    assert "evaluate_qms_competence_for_privilege" in source


def test_controlled_exemption_replaces_mutating_training_bypass() -> None:
    authorization_source = inspect.getsource(people_authorization_router)
    competence_source = inspect.getsource(audit_assignment_guard)
    assert "Controlled Exemption / Conditional Authorization" not in authorization_source or "controlled_exemption" in authorization_source
    assert "create_case_controlled_exemption" in authorization_source
    assert "active_controlled_authorization_exception" in competence_source
    assert "active_qm_bypass" not in competence_source


def test_decision_and_review_history_are_retained() -> None:
    privilege_fk = next(
        fk for fk in QualityPrivilegeDecision.__table__.foreign_keys
        if fk.parent.name == "privilege_id"
    )
    assert privilege_fk.ondelete == "RESTRICT"
    assert QualityAuthorizationCase.__tablename__ == "quality_authorization_cases"
    assert QualityAuthorizationCaseEvent.__tablename__ == "quality_authorization_case_events"
    assert QualityAuthorizationReview.__tablename__ == "quality_authorization_reviews"
    assert QualityControlledExemption.__tablename__ == "quality_controlled_exemptions"


def test_development_target_is_evidence_not_automatic_gate() -> None:
    source = inspect.getsource(people_authorization_router.decide_authorization_case)
    assert "INCOMPLETE_DEVELOPMENT_TARGET_APPROVAL" in source
    assert "incomplete_development_basis" in source
    assert "Record the approval basis" in source
    readiness = inspect.getsource(people_authorization_router._readiness)
    assert '"target_is_hard_gate": False' in readiness


def test_assignment_guard_keeps_assignment_specific_authority() -> None:
    source = inspect.getsource(audit_assignment_guard.evaluate_auditor_assignment)
    assert "LEAD_AUDITOR" in source
    assert "OBSERVER_AUDITOR" in inspect.getsource(audit_assignment_guard._privilege_types_for_assignment)
    assert "active_privilege" in source
    assert "scope_authorized" in source
    assert "training_current_verified" in source
    assert "capacity" in source
    assert "independence" in source
