from dataclasses import replace
from datetime import date, timedelta
from sqlalchemy import text

from amodb.apps.quality import management_review_router as review
from amodb.apps.quality import work_inbox_router as work
from amodb.apps.quality.tests.test_management_review_workflow import client  # noqa: F401
from amodb.apps.quality.tests.test_controlled_register_workflow import risk_body


def test_assignments_overdue_completed_and_watch_preferences_are_distinct(client):
    body = {**risk_body(), "due_date": (date.today() - timedelta(days=2)).isoformat()}
    response = client.post("/register-workspace/risk/register", json=body)
    assert response.status_code == 201, response.text
    own = response.json()
    peer = client.post("/register-workspace/risk/register", json={**body, "owner_user_id": "peer", "title": "Peer's risk assessment"}).json()
    assigned = client.get("/work-inbox/assigned-to-me").json()
    assert not assigned["source_errors"], assigned
    assert [r["record_id"] for r in assigned["items"]] == [own["id"]]
    overdue = client.get("/work-inbox/overdue").json()
    assert overdue["total"] == 1
    assert client.get("/work-inbox/completed").json()["total"] == 0
    assert client.get("/work-inbox/watching").json()["total"] == 0
    response = client.post("/work-inbox/watch", json={"source": "risks", "record_id": peer["id"]})
    assert response.status_code == 200, response.text
    assert client.post("/work-inbox/watch", json={"source": "risks", "record_id": peer["id"]}).json()["id"] == response.json()["id"]
    watched = client.get("/work-inbox/watching").json()
    assert watched["total"] == 1
    assert watched["items"][0]["record_id"] == peer["id"]
    assert watched["items"][0]["watching"]
    assert client.get("/register-workspace/risk/register/" + peer["id"]).json()["owner_user_id"] == "peer"
    assert client.delete("/work-inbox/watch/risks/" + peer["id"]).status_code == 200
    assert client.get("/work-inbox/watching").json()["total"] == 0
    response = client.put("/register-workspace/risk/register/" + own["id"], json={**body, "status": "CLOSED", "expected_version": own["version"]})
    assert response.status_code == 200, response.text
    assert client.get("/work-inbox/assigned-to-me").json()["total"] == 0
    assert client.get("/work-inbox/overdue").json()["total"] == 0
    assert client.get("/work-inbox/completed").json()["total"] == 1


def test_approvals_and_watch_records_preserve_tenant_and_permission_scope(client, monkeypatch):
    client.connection.execute(text("INSERT INTO qms_management_reviews (id,amo_id,title,owner_user_id,status,due_date,payload) VALUES ('review-a','tenant-a','Review awaiting approval','peer','PENDING_APPROVAL','2026-11-18','{}')"))
    client.connection.commit()
    result = client.get("/work-inbox/approvals").json()
    assert result["total"] == 1, result
    assert result["items"][0]["source"] == "reviews"
    assert client.get("/work-inbox/assigned-to-me").json()["total"] == 0
    assert client.post("/work-inbox/watch", json={"source": "untrusted_table", "record_id": "review-a"}).status_code == 422
    monkeypatch.setattr(work, "has_quality_permission", lambda db, ctx, permission: permission != "qms.management_review.manage")
    assert client.get("/work-inbox/approvals").json()["total"] == 0
    client.app.dependency_overrides[review.resolve_tenant_context] = lambda: replace(client.ctx, amo_id="tenant-b", user_id="outsider")
    assert client.post("/work-inbox/watch", json={"source": "reviews", "record_id": "review-a"}).status_code == 404
    assert client.get("/work-inbox/assigned-to-me").json()["total"] == 0


def test_inbox_summary_and_source_filter_follow_canonical_permissions(client):
    body = {**risk_body(), "due_date": (date.today() - timedelta(days=1)).isoformat()}
    own = client.post("/register-workspace/risk/register", json=body).json()
    client.post("/register-workspace/risk/register", json={**body, "owner_user_id": "peer", "title": "Another owner's risk"})
    summary = client.get("/work-inbox/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["source_errors"] == []
    assert summary.json()["assigned_to_me"] == 1
    assert summary.json()["overdue"] == 1
    assert summary.json()["completed"] == 0
    assert client.get("/work-inbox/assigned-to-me?source=risks").json()["items"][0]["record_id"] == own["id"]
    assert client.get("/work-inbox/assigned-to-me?source=audits").json()["total"] == 0
    assert client.get("/work-inbox/assigned-to-me?source=untrusted").status_code == 422


def test_governed_due_filters_and_source_owned_next_action(client):
    today = date.today()
    base = risk_body()
    for title, date_due in (
        ("Historical overdue exposure", today - timedelta(days=4)),
        ("Action due today", today),
        ("Upcoming task", today + timedelta(days=2)),
    ):
        created = client.post(
            "/register-workspace/risk/register",
            json={**base, "title": title, "due_date": date_due.isoformat()},
        )
        assert created.status_code == 201, created.text
    due_today = client.get("/work-inbox/assigned-to-me?source=risks&due=today")
    assert due_today.status_code == 200, due_today.text
    assert [row["title"] for row in due_today.json()["items"]] == ["Action due today"]
    soon = client.get("/work-inbox/assigned-to-me?source=risks&due=next-seven")
    assert soon.json()["total"] == 2
    overdue = client.get("/work-inbox/assigned-to-me?source=risks&sort=priority")
    assert overdue.json()["items"][0]["title"] == "Historical overdue exposure"
    alpha = client.get("/work-inbox/assigned-to-me?source=risks&sort=title")
    assert [row["title"] for row in alpha.json()["items"]] == sorted(
        row["title"] for row in alpha.json()["items"]
    )
    first = overdue.json()["items"][0]
    assert first["scope"] == "ASSIGNED"
    assert "risk" in first["next_action"].lower()
    assert first["route"].startswith("/maintenance/A/quality/risk/")
    assert client.get("/work-inbox/assigned-to-me?due=wrong").status_code == 422
    assert client.get("/work-inbox/assigned-to-me?sort=random").status_code == 422


def test_saved_work_filters_are_private_authorised_audited_and_removable(client):
    preset = {
        "title": "My audits due today",
        "view": "assigned-to-me",
        "q": "engine",
        "source": "audits",
        "due": "today",
        "sort": "title",
    }
    created = client.post("/work-inbox/saved-views", json=preset)
    assert created.status_code == 201, created.text
    view_id = created.json()["id"]
    assert created.json()["filters"]["source"] == "audits"
    listing = client.get("/work-inbox/saved-views")
    assert listing.status_code == 200, listing.text
    assert listing.json()["limit"] == 20
    assert listing.json()["items"] == [{
        "id": view_id,
        "title": preset["title"],
        "filters": {key: value for key, value in preset.items() if key != "title"},
    }]
    assert client.post("/work-inbox/saved-views", json={**preset, "title": "my AUDITS due today"}).status_code == 409
    assert client.post("/work-inbox/saved-views", json={**preset, "source": "unknown"}).status_code == 422

    client.app.dependency_overrides[review.resolve_tenant_context] = lambda: replace(
        client.ctx, amo_id="tenant-b", user_id="outsider",
    )
    assert client.get("/work-inbox/saved-views").json()["items"] == []
    assert client.delete("/work-inbox/saved-views/" + view_id).status_code == 404
    client.app.dependency_overrides[review.resolve_tenant_context] = lambda: client.ctx
    assert client.delete("/work-inbox/saved-views/" + view_id).json() == {"deleted": True}
    assert client.get("/work-inbox/saved-views").json()["items"] == []
    assert client.delete("/work-inbox/saved-views/" + view_id).status_code == 404
