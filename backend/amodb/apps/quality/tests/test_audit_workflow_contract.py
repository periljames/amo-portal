from types import SimpleNamespace

from amodb.apps.quality import router
from amodb.apps.quality.audit_workflow_contract import (
    STAGE_ORDER,
    WorkflowFacts,
    _audit_setup_ready,
    _stage_definitions,
)
from amodb.apps.quality.schemas import QMSAuditWorkspaceOut


def _facts(**overrides) -> WorkflowFacts:
    values = {
        "war_room_ready": True,
        "checklist_source_present": True,
        "checklist_total": 10,
        "checklist_completed": 10,
        "fieldwork_closed": True,
        "findings_total": 1,
        "findings_open": 1,
        "nc_findings_total": 1,
        "nc_findings_without_car": 0,
        "report_complete": True,
        "report_metric": "Uploaded",
        "cars_total": 1,
        "cars_open": 0,
        "evidence_total": 4,
        "required_car_evidence_missing": 0,
        "required_car_evidence_unverified": 0,
        "archive_count": 0,
        "audit_closed": False,
    }
    values.update(overrides)
    return WorkflowFacts(**values)


def _get_routes(path: str):
    return [
        route
        for route in router.routes
        if str(getattr(route, "path", "")) == path
        and "GET" in (getattr(route, "methods", None) or set())
    ]


def test_stage_order_matches_the_visible_audit_workspace():
    stages = _stage_definitions(_facts(), audit_ref="QAR/MO/26/001", audit_status="CAP_OPEN")
    assert tuple(stage["id"] for stage in stages) == STAGE_ORDER
    assert STAGE_ORDER == (
        "war-room",
        "checklist",
        "findings",
        "report",
        "cars",
        "evidence",
        "closeout",
    )


def test_setup_gate_requires_scope_and_applicable_criteria():
    complete = {
        "planned_start": "2026-09-11",
        "planned_end": "2026-09-12",
        "scope": "Line maintenance and release records",
        "criteria": "KCARs Part 145 and company CAME/MOE",
        "lead_auditor_user_id": "lead-1",
        "auditee": "Maintenance Manager",
        "auditee_email": None,
        "auditee_user_id": None,
    }

    assert _audit_setup_ready(SimpleNamespace(**complete)) is True
    assert _audit_setup_ready(SimpleNamespace(**{**complete, "scope": "  "})) is False
    assert _audit_setup_ready(SimpleNamespace(**{**complete, "criteria": None})) is False


def test_car_stage_cannot_complete_before_report_or_with_unlinked_nc():
    before_report = _stage_definitions(
        _facts(report_complete=False, report_metric="Pending"),
        audit_ref="QAR/MO/26/001",
        audit_status="IN_PROGRESS",
    )
    assert next(stage for stage in before_report if stage["id"] == "cars")["complete"] is False

    missing_car = _stage_definitions(
        _facts(nc_findings_without_car=1),
        audit_ref="QAR/MO/26/001",
        audit_status="CAP_OPEN",
    )
    assert next(stage for stage in missing_car if stage["id"] == "cars")["complete"] is False


def test_evidence_stage_requires_required_car_evidence_to_be_verified():
    stages = _stage_definitions(
        _facts(required_car_evidence_unverified=1),
        audit_ref="QAR/MO/26/001",
        audit_status="CAP_OPEN",
    )
    evidence = next(stage for stage in stages if stage["id"] == "evidence")
    assert evidence["complete"] is False
    assert "1 unverified" in evidence["metric"]


def test_closed_audit_is_presented_as_a_completed_immutable_workflow():
    stages = _stage_definitions(
        _facts(
            audit_closed=True,
            checklist_source_present=False,
            checklist_total=0,
            checklist_completed=0,
            fieldwork_closed=False,
            report_complete=False,
            cars_open=1,
            required_car_evidence_missing=1,
            required_car_evidence_unverified=1,
        ),
        audit_ref="QAR/MO/26/001",
        audit_status="CLOSED",
    )
    assert all(stage["complete"] for stage in stages)


def test_authoritative_workflow_routes_replace_legacy_handlers_once():
    for path in (
        "/quality/audits/{audit_id}/workspace",
        "/quality/audits/{audit_id}/workflow-check",
    ):
        routes = _get_routes(path)
        assert len(routes) == 1
        assert getattr(routes[0], "response_model", None) is QMSAuditWorkspaceOut
