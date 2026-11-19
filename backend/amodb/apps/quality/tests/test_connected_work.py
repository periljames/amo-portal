"""Connected inbox projections must preserve source authorization and tenant ownership."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from sqlalchemy import text

from amodb.apps.quality import work_inbox_related_router as related
from amodb.apps.quality.tests.test_management_review_workflow import client  # noqa: F401
from amodb.apps.quality import management_review_router as review


def _table(client, sql):
    prefix = "TEMP " if client.connection.dialect.name == "postgresql" else ""
    client.connection.execute(text("CREATE " + prefix + "TABLE " + sql))


def test_connected_training_steps_are_owned_bounded_and_correctly_blocked(client, monkeypatch):
    monkeypatch.setattr(related, "assert_quality_permission", lambda *args: None)
    monkeypatch.setattr(related, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(related, "has_quality_permission", lambda db, ctx, p: p == "qms.training.view")
    _table(client, "training_workflow_instances (id text,amo_id text,title text,status text,due_at date)")
    _table(client, "training_workflow_steps (id text,amo_id text,workflow_instance_id text,assigned_user_id text,label text,status text)")
    due = (date.today() - timedelta(days=2)).isoformat()
    client.connection.execute(text("""
        INSERT INTO training_workflow_instances VALUES
        ('w1','tenant-a','Document training','IN_PROGRESS',:due),
        ('w2','tenant-b','Different tenant training','IN_PROGRESS',:due)"""), {"due":due})
    client.connection.execute(text("""
        INSERT INTO training_workflow_steps VALUES
        ('s1','tenant-a','w1','chair','Complete competence check','READY'),
        ('s2','tenant-a','w1','chair','Supervisor sign-off','PENDING'),
        ('s3','tenant-a','w1','peer','Peer work','READY'),
        ('s4','tenant-b','w2','chair','Foreign tenant step','READY')"""))
    client.connection.commit()
    response = client.get("/work-inbox/related?source=training-steps")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source_errors"] == []
    assert result["total"] == 2
    assert {v["record_id"] for v in result["items"]} == {"s1", "s2"}
    assert [row["blocked"] for row in result["items"] if row["record_id"] == "s2"] == [True]
    assert all(row["scope"] == "ASSIGNED" for row in result["items"])
    assert client.get("/work-inbox/related?source=training-steps&category=overdue").json()["total"] == 2
    assert client.get("/work-inbox/related?source=training-steps&offset=1&limit=1").json()["total"] == 2
    assert len(client.get("/work-inbox/related?source=training-steps&offset=1&limit=1").json()["items"]) == 1
    assert client.get("/work-inbox/related?source=training-steps&q=supervisor").json()["total"] == 1
    assert client.get("/work-inbox/related?source=untrusted").status_code == 422
    client.app.dependency_overrides[review.resolve_tenant_context] = lambda: replace(
        client.ctx, amo_id="tenant-b", user_id="outsider",
    )
    assert client.get("/work-inbox/related?source=training-steps").json()["total"] == 0


def test_connected_document_review_never_exposes_others_manuscripts(client, monkeypatch):
    monkeypatch.setattr(related, "assert_quality_permission", lambda *args: None)
    monkeypatch.setattr(related, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(related, "has_quality_permission", lambda db, ctx, p: p == "qms.document.view")
    _table(client, "manuals (id text,tenant_id text,title text,code text)")
    _table(client, "document_review_plans (id text,tenant_id text,manual_id text,owner_user_id text,due_at date,status text)")
    client.connection.execute(text("""
        INSERT INTO manuals VALUES ('m1','tenant-a','Quality Manual','QM-01'),('m2','tenant-b','Private Manual','QM-B')
    """))
    client.connection.execute(text("""
        INSERT INTO document_review_plans VALUES
          ('a','tenant-a','m1','chair','2020-01-01','SCHEDULED'),
          ('b','tenant-a','m1','peer','2020-01-01','SCHEDULED'),
          ('c','tenant-b','m2','chair','2020-01-01','SCHEDULED'),
          ('d','tenant-a','m1','chair','2020-01-01','COMPLETED')
    """))
    client.connection.commit()
    response = client.get("/work-inbox/related?source=document-reviews")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["record_id"] == "a"
    assert "Quality Manual" in result["items"][0]["title"]
    assert "Private Manual" not in str(result)
    assert result["items"][0]["route"].endswith("/quality/documents/library")
    monkeypatch.setattr(related, "has_quality_permission", lambda *args: False)
    denied = client.get("/work-inbox/related?source=document-reviews").json()
    assert denied["total"] == 0
    assert denied["items"] == []


def test_connected_provider_approval_is_shared_not_individually_assigned(client, monkeypatch):
    monkeypatch.setattr(related, "assert_quality_permission", lambda *args: None)
    monkeypatch.setattr(related, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(related, "has_quality_permission", lambda db, ctx, p: p == "qms.external.manage")
    _table(client, "external_tenant_grants (id text,amo_id text,identity_id text,tenant_provider_id text,status text)")
    _table(client, "external_identities (id text,email text,verified_at timestamp)")
    _table(client, "external_tenant_providers (id text,amo_id text,supplier_id int)")
    _table(client, "procurement_suppliers (id int,amo_id text,legal_name text)")
    client.connection.execute(text("""
        INSERT INTO procurement_suppliers VALUES (1,'tenant-a','Provider A'),(2,'tenant-b','Private Provider')
    """))
    client.connection.execute(text("""
        INSERT INTO external_tenant_providers VALUES ('p1','tenant-a',1),('p2','tenant-b',2)
    """))
    client.connection.execute(text("""
        INSERT INTO external_identities VALUES
          ('i1','rep@example.test','2026-11-18'),
          ('i2','unverified@example.test',NULL),
          ('i3','private@example.test','2026-11-18')
    """))
    client.connection.execute(text("""
        INSERT INTO external_tenant_grants VALUES
          ('g1','tenant-a','i1','p1','PENDING'),
          ('g2','tenant-a','i2','p1','PENDING'),
          ('g3','tenant-b','i3','p2','PENDING')
    """))
    client.connection.commit()
    response = client.get("/work-inbox/related?source=provider-approvals")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["scope"] == "SHARED_REVIEW"
    assert data["items"][0]["record_id"] == "g1"
    assert "private@example.test" not in str(data)
    assert data["items"][0]["due_date"] is None
    assert data["items"][0]["route"].endswith("/quality/external-accounts?view=accounts&grant=g1")
    monkeypatch.setattr(related, "has_quality_permission", lambda db, ctx, p: p == "qms.audit.manage")
    assert client.get("/work-inbox/related?source=provider-approvals").json()["total"] == 0


def test_connected_unavailable_source_is_error_not_zero_work(client, monkeypatch):
    monkeypatch.setattr(related, "assert_quality_permission", lambda *args: None)
    monkeypatch.setattr(related, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(related, "has_quality_permission", lambda db, ctx, p: p == "qms.document.view")
    monkeypatch.setitem(related.SOURCES, "document-acknowledgements", {
        **related.SOURCES["document-acknowledgements"],
        "projection": "SELECT id,title,status,due_date FROM source_deliberately_unavailable",
    })
    result = client.get("/work-inbox/related?source=document-acknowledgements")
    assert result.status_code == 200
    data = result.json()
    assert data["total"] == 0
    assert data["source_errors"]
    assert data["source_errors"][0]["source"] == "Document acknowledgement"
