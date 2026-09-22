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
    routes = _routes(people_router.router) | _routes(people_authorization_router.router)
    assert ("/people/authorization-control/cases", "POST") in routes
    assert ("/people/authorization-control/cases/{case_id}/submit", "POST") in routes
    assert ("/people/authorization-control/cases/{case_id}/decision", "POST") in routes
    assert ("/people/authorization-control/authorizations/{privilege_id}/lifecycle", "POST") in routes
    assert ("/people/authorization-control/authorizations/{privilege_id}/reviews", "POST") in routes
    assert ("/people/authorization-control/controlled-exemptions/{exemption_id}/revoke", "POST") in routes
    assert not any(path == "/people/authorization-workspace" for path, _method in routes)
    assert not any(path.startswith("/people/authorization-cases") for path, _method in routes)
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


def test_amo_admin_inherits_all_quality_manager_authority() -> None:
    admin = tenant_security._QUALITY_ROLE_PERMISSIONS["AMO_ADMIN"]
    manager = tenant_security._QUALITY_ROLE_PERMISSIONS["QUALITY_MANAGER"]
    assert "qms.*" in admin
    for permission in (
        "qms.authorization.prepare",
        "qms.authorization.approve",
        "qms.authorization.review",
        "qms.authorization.exemption.approve",
        "qms.authorization.policy.manage",
    ):
        assert any(
            grant == "qms.*" or grant == permission
            for grant in admin
        )
        assert any(
            grant == "qms.*" or grant == permission
            for grant in manager
        )


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
    assert audit_assignment_guard._privilege_types_for_assignment("OBSERVER_AUDITOR") == ("AUDITOR",)
    assert audit_assignment_guard._privilege_types_for_assignment("ASSISTANT_AUDITOR") == ("AUDITOR",)
    assert "active_privilege" in source
    assert "scope_authorized" in source
    assert "training_current_verified" in source
    assert "capacity" in source
    assert "independence" in source


def test_read_only_people_access_is_bounded_to_self_service() -> None:
    permissions_source = inspect.getsource(people_authorization_router._permissions)
    assert '"self_service_only"' in permissions_source

    people_source = inspect.getsource(people_authorization_router.authorization_people)
    cases_source = inspect.getsource(people_authorization_router.list_authorization_cases)
    reviews_source = inspect.getsource(people_authorization_router.list_authorization_reviews)
    authorizations_source = inspect.getsource(people_authorization_router.list_authorizations)
    person_detail_source = inspect.getsource(people_authorization_router.authorization_person_detail)
    record_source = inspect.getsource(people_authorization_router.authorization_record)

    assert "_can_view_tenant_authorization_register" in people_source
    assert "_can_view_tenant_authorization_register" in cases_source
    assert "_can_view_tenant_authorization_register" in reviews_source
    assert "_can_view_tenant_authorization_register" in authorizations_source
    assert "_require_self_or_register_access" in person_detail_source
    assert "_require_self_or_register_access" in record_source


def test_case_file_includes_prior_authorization_review_history() -> None:
    source = inspect.getsource(people_authorization_router.get_authorization_case)
    assert "QualityAuthorizationReview" in source
    assert '"authorization_reviews"' in source
    assert "_review_dict" in source


def test_authorization_record_is_quality_record_not_training_certificate() -> None:
    source = inspect.getsource(people_authorization_router.authorization_record)
    assert "Quality Authorization Record" in source
    assert "Decision authority" in source
    assert "Next review due" in source
    assert "CONTROLLED EXEMPTION ACTIVE" in source
    assert "training certificate" not in source.lower()
    assert "sha256" not in source.lower()
    assert "storage_path" not in source.lower()


def test_actual_actor_is_recorded_for_decisions_reviews_and_exemptions() -> None:
    decision_source = inspect.getsource(people_authorization_router._record_privilege_decision)
    review_source = inspect.getsource(people_authorization_router.create_authorization_review)
    exemption_source = inspect.getsource(people_authorization_router._create_controlled_exemption)
    assert "decided_by_user_id=ctx.user_id" in decision_source
    assert "reviewed_by_user_id=ctx.user_id" in review_source
    assert "approved_by_user_id=ctx.user_id" in exemption_source


def test_rule_catalog_requires_preparation_authority_not_plain_people_read() -> None:
    route = next(
        route
        for route in people_router.router.routes
        if str(route.path) == "/people/rules" and "GET" in (getattr(route, "methods", None) or set())
    )
    dependency_source = inspect.getsource(route.endpoint)
    assert 'require_quality_permission("qms.authorization.prepare")' in dependency_source
