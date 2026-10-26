from datetime import date, datetime, timezone
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import Column, MetaData, Table, create_engine
from sqlalchemy.orm import Session
from amodb.apps.quality import reports_router as reports
from amodb.apps.quality.models import QMSAudit, QMSAuditFinding, CorrectiveActionRequest
from amodb.apps.accounts.models import User
from amodb.apps.training.models import TrainingRecord, TrainingCourse

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    selected = {
        QMSAudit: "id amo_id audit_ref title kind status planned_start planned_end actual_end created_at deleted_at",
        QMSAuditFinding: "id amo_id audit_id finding_ref description severity finding_type requirement_ref target_close_date closed_at created_at",
        CorrectiveActionRequest: "id amo_id car_number title program priority status due_date target_closure_date closed_at created_at",
        User: "id amo_id full_name",
        TrainingCourse: "id amo_id course_id course_name",
        TrainingRecord: "id amo_id user_id course_id completion_date valid_until verification_status record_status",
    }
    tables = {}
    for model, fields in selected.items():
        tables[model] = Table(model.__tablename__, metadata, *(Column(c.name, c.type, primary_key=c.primary_key) for c in model.__table__.columns if c.name in fields.split()))
    metadata.create_all(engine)
    with Session(engine) as session:
        for tenant in ("a", "b"):
            audit_id = uuid.uuid4()
            session.execute(tables[QMSAudit].insert(), dict(id=audit_id, amo_id=tenant, audit_ref=f"QAR/{tenant}", title="=Danger <script>", kind="INTERNAL", status="PLANNED", created_at=datetime(2026,10,1,tzinfo=timezone.utc)))
            session.execute(tables[QMSAuditFinding].insert(), dict(id=uuid.uuid4(), amo_id=tenant, audit_id=audit_id, finding_ref=f"F/{tenant}", description="Finding", severity="MINOR", finding_type="NON_CONFORMITY", created_at=datetime(2026,10,2,tzinfo=timezone.utc)))
            session.execute(tables[CorrectiveActionRequest].insert(), dict(id=uuid.uuid4(), amo_id=tenant, car_number=f"CAR/{tenant}", title="Corrective action", program="QUALITY", priority="HIGH", status="OPEN", created_at=datetime(2026,10,3,tzinfo=timezone.utc)))
            session.execute(tables[User].insert(), dict(id=tenant, amo_id=tenant, full_name=f"Person {tenant}"))
            session.execute(tables[TrainingCourse].insert(), dict(id=tenant, amo_id=tenant, course_id="HF", course_name="Human factors"))
            session.execute(tables[TrainingRecord].insert(), dict(id=tenant, amo_id=tenant, user_id=tenant, course_id=tenant, completion_date=date(2026,10,1), valid_until=date(2026,10,10), verification_status="VERIFIED", record_status="ACTIVE"))
        session.execute(tables[CorrectiveActionRequest].insert(), dict(id=uuid.uuid4(), amo_id="a", car_number="CAR/a/2", title="Second corrective action", program="QUALITY", priority="HIGH", status="OPEN", created_at=datetime(2026,10,4,tzinfo=timezone.utc)))
        session.commit()
        yield session

def snapshot(db, kind):
    return reports.report_snapshot(db, "a", "Tenant A", kind, date(2026,10,1), date(2026,10,31))

def test_tenant_and_period_filters_and_escaped_outputs(db):
    result = snapshot(db, "audit-performance")
    assert result["total"] == 1
    assert result["rows"][0][0] == "QAR/a"
    assert "'=Danger <script>" in reports.csv_output(result)
    assert "&lt;script&gt;" in reports.html_output(result)
    assert "<script>" not in reports.html_output(result)
    assert reports.report_snapshot(db, "a", "A", "audit-performance", date(2026,9,1), date(2026,9,30))["total"] == 0

def test_findings_exclude_deleted_audits_and_cross_tenant(db):
    assert snapshot(db, "finding-trends")["total"] == 1
    db.query(QMSAudit).filter(QMSAudit.amo_id == "a").update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
    assert snapshot(db, "finding-trends")["total"] == 0

def test_executive_uses_actual_counts(db):
    result = snapshot(db, "executive-dashboard")
    assert result["rows"] == [["Audits", "PLANNED", "1"], ["CARs", "OPEN", "2"]]
    assert result["summary"] == [{"label": "OPEN", "value": 2}, {"label": "PLANNED", "value": 1}]

def test_car_and_training_reports_use_owned_sources(db):
    cars = snapshot(db, "car-performance")
    assert cars["rows"][0][0] == "CAR/a"
    assert cars["summary"] == [{"label": "OPEN", "value": 2}]
    training = snapshot(db, "training-compliance")
    assert training["rows"] == [["Person a", "HF", "Human factors", "2026-10-01", "2026-10-10", "VERIFIED", "EXPIRED"]]
    assert "not a role-requirement" in training["population"]

def test_rejects_invalid_period_and_partial_outputs(db, monkeypatch):
    with pytest.raises(HTTPException) as failure:
        reports.report_snapshot(db, "a", "A", "audit-performance", date(2026,11,1), date(2026,10,1))
    assert failure.value.status_code == 422
    monkeypatch.setattr(reports, "MAX_ROWS", 0)
    with pytest.raises(HTTPException) as failure:
        snapshot(db, "audit-performance")
    assert failure.value.status_code == 413

def test_report_routes_require_distinct_view_and_export_permissions(monkeypatch):
    from amodb.apps.quality import tenant_security
    from types import SimpleNamespace
    seen = []
    def enforce(**kwargs):
        seen.append(kwargs["permission"])
        if kwargs["permission"] == "qms.reports.export":
            raise HTTPException(403, "Export permission required")
        return kwargs["ctx"]
    monkeypatch.setattr(tenant_security, "_enforce_quality_permission", enforce)
    ctx = SimpleNamespace(amo_id="a")
    for route in reports.router.routes:
        guard = route.dependant.dependencies[0].call
        if route.path.endswith("/output"):
            with pytest.raises(HTTPException) as failure:
                guard(ctx, object(), object())
            assert failure.value.status_code == 403
        else:
            assert guard(ctx, object(), object()) is ctx
    assert seen == ["qms.reports.view", "qms.reports.export"]
