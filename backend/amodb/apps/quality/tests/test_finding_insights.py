import pytest
from sqlalchemy import text

from amodb.apps.quality import finding_insights_router as insights
from amodb.apps.quality.tests.test_management_review_workflow import client  # noqa: F401


@pytest.fixture
def findings(client, monkeypatch):
    client.app.include_router(insights.router)
    monkeypatch.setattr(insights, "assert_quality_permission", lambda db, ctx, permission: client.permissions.append(permission))
    monkeypatch.setattr(insights, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    connection = client.connection
    prefix = "TEMP " if connection.dialect.name == "postgresql" else ""
    connection.execute(text(f"CREATE {prefix}TABLE qms_audit_findings (id text,amo_id text,audit_id text,severity text,created_at timestamp,closed_at timestamp)"))
    connection.execute(text(f"CREATE {prefix}TABLE quality_assurance_controls (id text,amo_id text,status text,approval_status text,process_area text)"))
    connection.execute(text(f"CREATE {prefix}TABLE quality_assurance_evidence_links (id text,amo_id text,control_id text,source_type text,source_id text,evidence_status text,invalidated_at timestamp,valid_until date)"))
    connection.execute(text("INSERT INTO qms_audits (id,amo_id,title,deleted_at) VALUES ('audit-a','tenant-a','A',NULL),('audit-b','tenant-b','B',NULL),('deleted-a','tenant-a','Deleted','2026-01-01')"))
    for record_id, amo, audit, severity, raised, closed in [
        ("f1", "tenant-a", "audit-a", "MAJOR", "2026-01-10", "2026-03-01"),
        ("f2", "tenant-a", "audit-a", "MINOR", "2026-02-10", None),
        ("f3", "tenant-a", "audit-a", "CRITICAL", "2026-02-14", None),
        ("old", "tenant-a", "audit-a", "MINOR", "2025-02-14", "2026-03-02"),
        ("other", "tenant-b", "audit-b", "CRITICAL", "2026-01-01", None),
        ("mismatch", "tenant-a", "audit-b", "CRITICAL", "2026-01-01", None),
        ("deleted", "tenant-a", "deleted-a", "CRITICAL", "2026-01-01", None),
    ]:
        connection.execute(text("INSERT INTO qms_audit_findings (id,amo_id,audit_id,severity,created_at,closed_at) VALUES (:id,:amo,:audit,:severity,:raised,:closed)"), {"id": record_id, "amo": amo, "audit": audit, "severity": severity, "raised": raised, "closed": closed})
    connection.execute(text("INSERT INTO quality_assurance_controls VALUES ('c1','tenant-a','ACTIVE','APPROVED','Engineering'),('c2','tenant-a','ACTIVE','APPROVED','Engineering'),('draft','tenant-a','ACTIVE','DRAFT','Wrong'),('cross','tenant-b','ACTIVE','APPROVED','Other tenant')"))
    for record_id, control, source, status, expiry, invalidated in [
        ("l1", "c1", "f1", "VERIFIED", None, None),
        ("l2", "c2", "f1", "VERIFIED", None, None),
        ("l3", "c1", "f2", "LINKED", None, None),
        ("l4", "draft", "f2", "VERIFIED", None, None),
        ("l5", "c1", "f3", "VERIFIED", "2000-01-01", None),
        ("l6", "c1", "f3", "VERIFIED", None, "2026-01-01"),
        ("l7", "cross", "f3", "VERIFIED", None, None),
    ]:
        connection.execute(text("INSERT INTO quality_assurance_evidence_links VALUES (:id,'tenant-a',:control,'FINDING',:source,:status,:invalidated,:expiry)"), {"id": record_id, "control": control, "source": source, "status": status, "expiry": expiry, "invalidated": invalidated})
    connection.commit()
    return client


def test_severity_uses_real_cohort_and_tenant_ownership(findings):
    response = findings.get("/findings/insights?view=by-severity&year=2026")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 3 and data["open"] == 2
    assert {group["key"]: group["total"] for group in data["groups"]} == {"MAJOR": 1, "MINOR": 1, "CRITICAL": 1}
    assert "qms.finding.view" in findings.permissions


def test_process_mapping_requires_verified_current_approved_same_tenant_links(findings):
    data = findings.get("/findings/insights?view=by-process&year=2026").json()
    assert data["groups"] == [{"key": "Engineering", "total": 1, "open": 0}]
    assert data["unmapped"] == 2
    condition = insights.process_mapping_condition("f", matching=True)
    ids = findings.connection.execute(text(f"SELECT f.id FROM qms_audit_findings f WHERE f.amo_id='tenant-a' AND {condition}"), {"quality_process": "Engineering"}).scalars().all()
    assert ids == ["f1"]


def test_monthly_events_include_closures_of_previous_year_findings(findings):
    data = findings.get("/findings/insights?view=trends&year=2026").json()
    assert len(data["months"]) == 12
    assert data["months"][0] == {"month": "2026-01", "raised": 1, "closed": 0}
    assert data["months"][1] == {"month": "2026-02", "raised": 2, "closed": 0}
    assert data["months"][2] == {"month": "2026-03", "raised": 0, "closed": 2}
    assert findings.get("/findings/insights?view=trends&year=2200").status_code == 422
    assert findings.get("/findings/insights?view=by-severity").status_code == 200
