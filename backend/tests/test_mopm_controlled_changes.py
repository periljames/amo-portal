from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from amodb.apps.quality import canonical_core_router as legacy
from amodb.apps.quality.mission_change_policy import CONTROLLED_CHANGE_TYPES, mission_gate_template
from amodb.apps.quality.mission_router import CAPABILITY_ADDITION_GATE_TEMPLATE, MissionCreate, MissionDecisionCreate, mission_readiness
from amodb.apps.quality.mission_lifecycle_guard_router import authority_decision_evidence, _authority_evidence


@pytest.mark.parametrize("kind", sorted(CONTROLLED_CHANGE_TYPES))
def test_controlled_changes_start_with_required_unpassed_evidence_gates(kind):
    template = mission_gate_template(kind, CAPABILITY_ADDITION_GATE_TEMPLATE)
    assert {row["gate_code"] for row in template} == {"CHANGE_SCOPE", "SAFETY_ASSESSMENT", "CONTROLLED_DOCUMENTS", "PERSONNEL_READINESS", "AUTHORITY_REQUIREMENTS"}
    gates = [SimpleNamespace(id=row["gate_code"], gate_code=row["gate_code"], title=row["title"], status="PENDING", evidence_status="UNLINKED", gate_type="HARD", blocking_reason=None) for row in template]
    assert not mission_readiness(gates)["ready_for_quality_self_evaluation"]


def test_original_capability_template_is_preserved():
    assert mission_gate_template("CAPABILITY_ADDITION", CAPABILITY_ADDITION_GATE_TEMPLATE) is CAPABILITY_ADDITION_GATE_TEMPLATE


@pytest.mark.parametrize("extra", [{}, {"scope": {"affected_scope": "  "}, "description": "A meaningful description"}, {"scope": {"affected_scope": "MOPM 1.9"}, "description": "short"}])
def test_change_requests_reject_missing_scope_or_description_before_storage(extra):
    with pytest.raises(ValidationError):
        MissionCreate(mission_type="PROCEDURE_CHANGE", title="Change request", **extra)


def test_change_requests_trim_titles_and_keep_default_manual_basis():
    change = MissionCreate(mission_type="PROCEDURE_CHANGE", title="  Update procedure  ", scope={"affected_scope": "MOPM 1.9"}, description="Update the controlled notification procedure")
    assert change.title == "Update procedure"
    assert change.regulatory_basis == ["MOPM 1.9; 1.10"]


@pytest.mark.parametrize("operation", ["create", "update", "delete", "action"])
def test_legacy_write_routes_cannot_bypass_governed_change_approvals(operation):
    with pytest.raises(HTTPException) as error:
        if operation == "action":
            legacy.qms_workflow_action("change-control", "existing-record", "approve", None, {}, None, None)
        elif operation == "create":
            legacy.generic_qms_create("change-control/new", None, {"status": "APPROVED"}, None, None)
        elif operation == "update":
            legacy.generic_qms_update("change-control/existing-record", None, {"status": "APPROVED"}, None, None)
        else:
            legacy.generic_qms_delete("change-control/existing-record", None, None, None)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "GOVERNED_CHANGE_REQUIRED"


@pytest.fixture
def evidence_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as db:
        db.execute(text("CREATE TABLE document_evidence_assets (id text, tenant_id text, filename text, sha256 text, size_bytes int, category text, created_at text)"))
        db.execute(text("CREATE TABLE document_retention_dispositions (tenant_id text, source_type text, source_id text, status text)"))
        for ident, tenant, category in [("valid", "amo-a", "AUTHORITY"), ("foreign", "amo-b", "AUTHORITY"), ("general", "amo-a", "GENERAL"), ("disposed", "amo-a", "AUTHORITY")]:
            db.execute(text("INSERT INTO document_evidence_assets VALUES (:id,:tenant,:filename,:hash,20,:category,'2026-10-22')"), {"id":ident,"tenant":tenant,"filename":ident+".pdf","hash":"a"*64,"category":category})
        db.execute(text("INSERT INTO document_retention_dispositions VALUES ('amo-a','EVIDENCE_ASSET','disposed','DISPOSED')"))
        yield db
    engine.dispose()


@pytest.mark.parametrize("stage", ["AUTHORITY_SUBMISSION", "AUTHORITY_ACCEPTANCE"])
@pytest.mark.parametrize("asset", [None, "foreign", "general", "disposed", "missing"])
def test_approved_authority_decisions_require_available_tenant_authority_evidence(evidence_db, stage, asset):
    payload = MissionDecisionCreate(decision_type=stage, status="APPROVED", rationale="Recorded decision", evidence_asset_id=asset)
    with pytest.raises(HTTPException) as error:
        authority_decision_evidence(evidence_db, amo_id="amo-a", payload=payload)
    assert error.value.status_code == 422


def test_authority_evidence_is_selected_by_filename_and_snapshot_keeps_checksum(evidence_db):
    assert [row["asset_id"] for row in _authority_evidence(evidence_db, amo_id="amo-a", search="valid")] == ["valid"]
    payload = MissionDecisionCreate(decision_type="AUTHORITY_ACCEPTANCE", status="APPROVED", rationale="Recorded decision", evidence_asset_id="valid")
    snapshot = authority_decision_evidence(evidence_db, amo_id="amo-a", payload=payload)
    assert snapshot["asset_id"] == "valid" and snapshot["sha256"] == "a"*64
