from dataclasses import replace
import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amodb.apps.quality import canonical_router
from amodb.apps.quality import management_review_router as review
from amodb.apps.quality import controlled_register_router as controlled
from amodb.apps.quality import work_inbox_router as work
from amodb.apps.quality.canonical_core_router import _require_governed_change_write
from amodb.apps.quality.tenant_security import TenantContext
from amodb.database import get_read_db, get_write_db


@pytest.fixture(params=["sqlite", "postgres"])
def client(monkeypatch, request):
    postgres = request.param == "postgres"
    if postgres and not os.environ.get("QMS_TEST_POSTGRES_URL"):
        pytest.skip("Set QMS_TEST_POSTGRES_URL to verify PostgreSQL using session-private temporary tables.")
    engine = create_engine(os.environ["QMS_TEST_POSTGRES_URL"]) if postgres else create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    try:
        prefix = "TEMP " if postgres else ""
        connection.execute(text(f"CREATE {prefix}TABLE users (id text, amo_id text, is_active boolean, first_name text, last_name text, email text)"))
        connection.execute(text("INSERT INTO users VALUES ('chair','tenant-a',true,'Quality','Chair','chair@example.test'),('peer','tenant-a',true,'Peer','Owner','peer@example.test'),('outsider','tenant-b',true,'Other','Tenant','other@example.test')"))
        connection.execute(text("ALTER TABLE users ADD COLUMN full_name text"))
        for table in {review.MEETINGS, review.ACTIONS, work.WATCH_TABLE, *[s["table"] for s in work.SOURCES.values()], *[s["table"] for s in controlled.SOURCE_SPECS.values()]}:
            payload_type = "jsonb" if postgres else "text"
            connection.execute(text(f"CREATE {prefix}TABLE {table} (id text primary key, amo_id text, title text, description text, owner_user_id text, due_date date, status text, source_type text, payload {payload_type}, created_at timestamp, created_by text, updated_at timestamp, updated_by text, deleted_at timestamp, assigned_to_user_id text, lead_auditor_user_id text, observer_auditor_user_id text, assistant_auditor_user_id text, auditee_user_id text, planned_end date, planned_start date)"))
        if postgres:
            # All writes, including audit history, are confined to this database
            # connection's temporary schema. No tenant evidence is manufactured.
            connection.execute(text("CREATE TEMP TABLE qms_activity_logs (LIKE public.qms_activity_logs INCLUDING DEFAULTS)"))
        else:
            connection.execute(text("CREATE TABLE qms_activity_logs (id text,amo_id text,actor_user_id text,action text,module text,entity_type text,entity_id text,previous_value text,new_value text,created_at timestamp)"))
        connection.commit()
    except Exception:
        connection.close()
        engine.dispose()
        raise
    ctx = TenantContext(amo_code="A", amo_id="tenant-a", user_id="chair", is_superuser=False)
    app = FastAPI()
    app.include_router(review.router)
    app.include_router(controlled.router)
    app.include_router(work.router)
    app.dependency_overrides[review.resolve_tenant_context] = lambda: ctx
    def db():
        with Session(bind=connection) as session:
            yield session
    app.dependency_overrides[get_read_db] = db
    app.dependency_overrides[get_write_db] = db
    permissions = []
    monkeypatch.setattr(review, "assert_quality_permission", lambda db, ctx, permission: permissions.append(permission))
    monkeypatch.setattr(review, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(controlled, "assert_quality_permission", lambda db, ctx, permission: permissions.append(permission))
    monkeypatch.setattr(controlled, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(work, "assert_quality_permission", lambda db, ctx, permission: permissions.append(permission))
    monkeypatch.setattr(work, "has_quality_permission", lambda *args, **kwargs: True)
    monkeypatch.setattr(work, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    if not postgres:
        monkeypatch.setattr(review, "_log_qms_activity", lambda *args, **kwargs: None)
    with TestClient(app) as api:
        api.ctx = ctx
        api.app = app
        api.permissions = permissions
        api.connection = connection
        yield api
    connection.close()
    engine.dispose()


def meeting_body():
    return {"title": "Quarterly management review", "review_date": "2026-11-18", "chair_user_id": "chair",
            "attendee_user_ids": ["chair"], "agenda": "Performance, resources and actions", "inputs": [], "minutes": "", "decisions": []}


def create(client):
    result = client.post("/management-review/workspace/meetings", json=meeting_body())
    assert result.status_code == 201, result.text
    return result.json()


def transition(client, row, target, kind="meetings"):
    return client.post(f"/management-review/workspace/{kind}/{row['id']}/transition",
                       json={"status": target, "expected_version": row["version"], "reason": "Retained decision and supporting evidence checked."})


def test_complete_meeting_and_verified_action_lifecycle(client):
    row = create(client)
    row = transition(client, row, "SCHEDULED").json()
    row = transition(client, row, "IN_PROGRESS").json()
    response = transition(client, row, "PENDING_APPROVAL")
    assert response.status_code == 422
    body = {**meeting_body(), "expected_version": row["version"], "inputs": [{"topic": "Audit results", "summary": "Reviewed retained audit findings", "source_reference": "Audit register"}],
            "minutes": "Management considered resources and agreed a corrective improvement.",
            "decisions": [{"id": "decision-1", "title": "Improve controls", "rationale": "Review found a gap in the current controls."}]}
    response = client.put(f"/management-review/workspace/meetings/{row['id']}", json=body)
    assert response.status_code == 200, response.text
    row = response.json()
    action_body = {"title": "Implement agreed control", "description": "Implement and retain evidence", "owner_user_id": "chair", "due_date": "2026-11-20", "decision_id": "decision-1"}
    response = client.post(f"/management-review/workspace/meetings/{row['id']}/actions", json=action_body)
    assert response.status_code == 201, response.text
    action = response.json()
    row = transition(client, row, "PENDING_APPROVAL").json()
    row = transition(client, row, "APPROVED").json()
    assert row["payload"]["approval"]["by"] == "chair"
    assert transition(client, row, "CLOSED").status_code == 422
    action = transition(client, action, "IN_PROGRESS", "actions").json()
    assert transition(client, action, "PENDING_VERIFICATION", "actions").status_code == 422
    response = client.put(f"/management-review/workspace/actions/{action['id']}", json={**action_body, "expected_version": action["version"], "completion_evidence": "Control implemented; retained evidence verified against decision."})
    assert response.status_code == 200, response.text
    action = response.json()
    action = transition(client, action, "PENDING_VERIFICATION", "actions").json()
    action = transition(client, action, "CLOSED", "actions").json()
    assert action["payload"]["verification"]["by"] == "chair"
    response = transition(client, row, "CLOSED")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CLOSED"
    assert transition(client, action, "IN_PROGRESS", "actions").status_code == 409
    detail = client.get(f"/management-review/workspace/meetings/{row['id']}").json()
    assert detail["actions"][0]["status"] == "CLOSED"
    assert len(detail["payload"]["history"]) == 7
    transitions = [event for event in detail["payload"]["history"] if event["event"] not in {"REVIEW_CREATED", "REVIEW_UPDATED"}]
    assert len(transitions) == 5
    assert all(event["reason"] == "Retained decision and supporting evidence checked." for event in transitions)
    assert action["payload"]["history"][-1]["reason"] == "Retained decision and supporting evidence checked."
    assert "qms.management_review.manage" in client.permissions


def test_stale_versions_tenant_boundaries_and_invalid_owners(client):
    row = create(client)
    assert transition(client, row, "APPROVED").status_code == 409
    assert transition(client, row, "SCHEDULED").status_code == 200
    assert transition(client, row, "SCHEDULED").status_code == 409
    assert client.post("/management-review/workspace/meetings", json={**meeting_body(), "chair_user_id": "outsider"}).status_code == 422
    client.app.dependency_overrides[review.resolve_tenant_context] = lambda: replace(client.ctx, amo_id="tenant-b", user_id="outsider")
    assert client.get(f"/management-review/workspace/meetings/{row['id']}").status_code == 404
    assert client.get("/management-review/workspace").json()["total"] == 0
    assert client.put(f"/management-review/workspace/meetings/{row['id']}", json={**meeting_body(), "expected_version": 1}).status_code == 404


def test_decision_links_and_date_validation(client):
    row = create(client)
    response = client.post(f"/management-review/workspace/meetings/{row['id']}/actions", json={"title": "Follow up", "owner_user_id": "chair", "due_date": "2026-11-20", "decision_id": "missing"})
    assert response.status_code == 422
    assert client.post("/management-review/workspace/meetings", json={**meeting_body(), "title": "   "}).status_code == 422
    assert client.post("/management-review/workspace/meetings", json={**meeting_body(), "review_date": "not-a-date"}).status_code == 422
    assert client.get("/management-review/workspace?view=unknown").status_code == 422


def test_governed_api_precedes_fallback_and_generic_writes_are_blocked():
    for router in (canonical_router.router, canonical_router.core_router):
        positions = {r.endpoint: i for i, r in enumerate(router.routes)}
        assert positions[review.create_meeting] < positions[canonical_router.generic_qms_create]
    with pytest.raises(HTTPException) as error:
        _require_governed_change_write("management-review")
    assert error.value.status_code == 409
