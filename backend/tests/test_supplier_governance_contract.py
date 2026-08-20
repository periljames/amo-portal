from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from amodb.apps.procurement import supplier_governance_schemas as schemas
from amodb.apps.quality.audit_assignment_guard import _development_rule
from amodb.apps.quality.people_models import QualityPrivilegeRule


BACKEND = Path(__file__).resolve().parents[1]
PROCUREMENT = BACKEND / "amodb" / "apps" / "procurement"
QUALITY = BACKEND / "amodb" / "apps" / "quality"
FRONTEND = BACKEND.parent / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _policy_payload() -> dict:
    return {
        "risk_review_days": {
            "LOW": 730,
            "MEDIUM": 365,
            "HIGH": 180,
            "CRITICAL": 90,
        },
        "re_evaluation_rules": {
            "expiry_lead_days": 30,
            "lookback_days": 180,
            "rejected_inspection_threshold": 2,
            "active_hold_threshold": 1,
            "action_due_days": 14,
        },
        "require_independent_review": True,
        "conditional_approval_allowed": True,
    }


def test_supplier_governance_python_sources_parse() -> None:
    for path in [
        PROCUREMENT / "supplier_governance_models.py",
        PROCUREMENT / "supplier_governance_schemas.py",
        PROCUREMENT / "supplier_governance_service.py",
        PROCUREMENT / "supplier_governance_router.py",
        QUALITY / "audit_assignment_guard.py",
        BACKEND / "amodb" / "alembic" / "versions" / "procurement_20260820_supplier_governance.py",
    ]:
        ast.parse(_read(path), filename=str(path))


def test_tenant_policy_has_no_silent_risk_interval_defaults() -> None:
    parsed = schemas.SupplierGovernancePolicyUpdate.model_validate(_policy_payload())
    assert parsed.risk_review_days == {
        "LOW": 730,
        "MEDIUM": 365,
        "HIGH": 180,
        "CRITICAL": 90,
    }

    missing = _policy_payload()
    missing["risk_review_days"] = {"LOW": 730, "MEDIUM": 365, "HIGH": 180}
    with pytest.raises(ValidationError):
        schemas.SupplierGovernancePolicyUpdate.model_validate(missing)

    extra = _policy_payload()
    extra["risk_review_days"] = {
        "LOW": 730,
        "MEDIUM": 365,
        "HIGH": 180,
        "CRITICAL": 90,
        "PORTAL_DEFAULT": 365,
    }
    with pytest.raises(ValidationError):
        schemas.SupplierGovernancePolicyUpdate.model_validate(extra)


def test_evaluation_template_requires_unique_weighted_criteria() -> None:
    with pytest.raises(ValidationError):
        schemas.SupplierEvaluationTemplateCreate(
            code="supplier",
            name="Supplier evaluation",
            pass_threshold=Decimal("80"),
            criteria=[
                schemas.SupplierCriterionCreate(
                    criterion_key="TRACEABILITY",
                    sequence_no=1,
                    label="Traceability",
                    weight=Decimal("0"),
                )
            ],
        )

    with pytest.raises(ValidationError):
        schemas.SupplierEvaluationTemplateCreate(
            code="supplier",
            name="Supplier evaluation",
            pass_threshold=Decimal("80"),
            criteria=[
                schemas.SupplierCriterionCreate(
                    criterion_key="TRACEABILITY",
                    sequence_no=1,
                    label="Traceability",
                ),
                schemas.SupplierCriterionCreate(
                    criterion_key="traceability",
                    sequence_no=2,
                    label="Duplicate traceability",
                ),
            ],
        )


def test_evaluation_requires_declared_scope_and_conditional_conditions() -> None:
    with pytest.raises(ValidationError):
        schemas.SupplierEvaluationCreate(template_id="template-id", intended_scope=[])

    with pytest.raises(ValidationError):
        schemas.SupplierEvaluationReview(
            expected_version=1,
            decision="CONDITIONALLY_APPROVE",
            rationale="Restricted approval pending evidence.",
            conditions=[],
        )


def test_supervised_development_is_explicit_and_never_applies_to_lead() -> None:
    governed = QualityPrivilegeRule(
        amo_id="amo-1",
        privilege_code="AUDITOR_DEV",
        title="Auditor development",
        privilege_type="AUDITOR",
        required_training_course_codes=["AUDITOR"],
        scope_schema={
            "supervised_development": True,
            "allowed_assignment_roles": ["OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"],
        },
    )
    assert _development_rule(governed, "OBSERVER_AUDITOR") is True
    assert _development_rule(governed, "ASSISTANT_AUDITOR") is True
    assert _development_rule(governed, "LEAD_AUDITOR") is False

    ordinary = QualityPrivilegeRule(
        amo_id="amo-1",
        privilege_code="AUDITOR",
        title="Auditor",
        privilege_type="AUDITOR",
        required_training_course_codes=["AUDITOR"],
        scope_schema={},
    )
    assert _development_rule(ordinary, "OBSERVER_AUDITOR") is False


def test_supplier_approval_scope_and_assignment_paths_fail_closed() -> None:
    service = _read(PROCUREMENT / "supplier_governance_service.py")
    inventory_registration = _read(BACKEND / "amodb" / "apps" / "inventory" / "__init__.py")
    assignment_guard = _read(QUALITY / "audit_assignment_guard.py")

    assert 'status=procurement_models.ApprovalScopeStatus.DRAFT' in service
    assert '"SUPPLIER_EVALUATION_REQUIRED"' in service
    assert 'evaluation.status not in APPROVED_EVALUATION_STATES' in service
    assert 'create_governed_scope' in service
    assert 'supplier_governance_router' in inventory_registration
    assert inventory_registration.index('router.include_router(supplier_governance_router)') < inventory_registration.index('router.include_router(procurement_router)')

    assert '"mode": "CONFIGURATION_REQUIRED"' in assignment_guard
    assert '"eligible": False' in assignment_guard
    assert 'LEGACY_COMPATIBILITY' not in assignment_guard


def test_re_evaluation_uses_real_bounded_receiving_and_hold_aggregates() -> None:
    service = _read(PROCUREMENT / "supplier_governance_service.py")
    assert 'ProcurementReceivingInspection.completed_at >= cutoff' in service
    assert 'group_by(procurement_models.ProcurementPurchaseOrder.supplier_id)' in service
    assert 'ProcurementQualityHold.target_type == "SUPPLIER"' in service
    assert 'group_by(procurement_models.ProcurementQualityHold.target_id)' in service
    assert '.limit(5000).all()' in service


def test_frontend_no_longer_auto_passes_governed_procurement_decisions() -> None:
    sections = _read(FRONTEND / "pages" / "procurement" / "ProcurementSections.tsx")
    forms = _read(FRONTEND / "pages" / "procurement" / "ProcurementForms.tsx")
    actions = _read(FRONTEND / "pages" / "procurement" / "procurementActions.ts")

    assert 'evaluation_score: 100' not in sections
    assert 'Approved through controlled supplier review.' not in sections
    assert 'Independent Quality release completed.' not in sections
    assert 'documentationComplete: "yes"' not in sections
    assert 'supplierScope: "yes"' not in sections
    assert 'disposition: "ACCEPTED"' not in sections

    for required_field in ["decisionReason", "releaseComment", "evaluationNotes"]:
        assert required_field in forms or required_field in actions
