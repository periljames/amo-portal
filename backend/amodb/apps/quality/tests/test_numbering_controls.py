from types import SimpleNamespace
from datetime import date
import pytest
from fastapi import HTTPException
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models, numbering
from amodb.apps.quality import canonical_core_router as router


@pytest.fixture
def tenant(db_session, monkeypatch):
    monkeypatch.setattr(numbering, "server_date", lambda: date(2026, 10, 26))
    monkeypatch.setattr(router, "server_date", lambda: date(2026, 10, 26))
    monkeypatch.setattr(router, "read_rules", lambda *args: {"audit_prefix": "QA"})
    amo = accounts.AMO(amo_code="NUMBER", name="Number tenant", login_slug="number")
    other = accounts.AMO(amo_code="OTHER", name="Other tenant", login_slug="other")
    db_session.add_all([amo, other]); db_session.flush()
    monkeypatch.setattr(router, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(router, "_log_qms_activity", lambda *args, **kwargs: None)
    return SimpleNamespace(amo_id=amo.id, amo_code=amo.amo_code, user_id=None), other


def payload(**updates):
    return {"prefix": "QA", "scope": "MO", "expected_period": "2026", "expected_date_format": "YY", "last_value": 0, "expected_last_value": 0, "reason": "Starting a fresh reference series", "confirmed": True, **updates}


def test_reset_empty_series_then_allocate_and_reject_stale_change(db_session, tenant):
    ctx, _ = tenant
    result = router.reset_numbering_series(None, payload(), ctx, db_session)
    assert result["next_value"] == 1
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO") == "QA/MO/26/001"
    with pytest.raises(HTTPException) as error:
        router.reset_numbering_series(None, payload(), ctx, db_session)
    assert error.value.status_code == 409


def test_reset_cannot_reuse_issued_audit_or_car_numbers(db_session, tenant):
    ctx, _ = tenant
    db_session.add(models.QMSAudit(amo_id=ctx.amo_id, domain=models.QMSDomain.AMO, kind=models.QMSAuditKind.INTERNAL, audit_ref="QA/MO/26/012", reference_family="QA", unit_code="MO", ref_year=26, ref_sequence=12, title="Preserved record"))
    db_session.flush()
    with pytest.raises(HTTPException) as error:
        router.reset_numbering_series(None, payload(), ctx, db_session)
    assert error.value.status_code == 409
    assert db_session.query(models.QMSAudit).filter_by(amo_id=ctx.amo_id).one().audit_ref == "QA/MO/26/012"


def test_series_adjustment_never_changes_other_tenant(db_session, tenant):
    ctx, other = tenant
    db_session.add(models.QMSAuditReferenceCounter(amo_id=other.id, reference_family="QA", unit_code="MO", ref_year=26, last_value=41)); db_session.flush()
    router.reset_numbering_series(None, payload(last_value=6), ctx, db_session)
    assert db_session.query(models.QMSAuditReferenceCounter).filter_by(amo_id=other.id).one().last_value == 41
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO", digits=4) == "QA/MO/26/0007"


@pytest.mark.parametrize("updates", [{"last_value": -1}, {"last_value": True}, {"prefix": "QA/NEW"}, {"year": 2026}, {"reason": "short"}, {"confirmed": False}])
def test_reset_requires_valid_scoped_confirmed_input(db_session, tenant, updates):
    ctx, _ = tenant
    with pytest.raises(HTTPException) as error:
        router.reset_numbering_series(None, payload(**updates), ctx, db_session)
    assert error.value.status_code == 422
    assert db_session.query(models.QMSAuditReferenceCounter).count() == 0


def test_follow_up_validation_conflict_and_governed_escalation(db_session, tenant):
    ctx, _ = tenant
    before = router.get_follow_up_controls(ctx, db_session)["settings"]
    result = router.update_follow_up_controls(None, {"expected_settings": before, "report_due_days": 10, "auto_escalation_enabled": False}, ctx, db_session)
    assert result["settings"]["report_due_days"] == 10
    assert result["settings"]["auto_escalation_enabled"] is True
    with pytest.raises(HTTPException) as error:
        router.update_follow_up_controls(None, {"expected_settings": before, "report_due_days": 9}, ctx, db_session)
    assert error.value.status_code == 409


def test_configured_prefixes_drive_real_allocators(db_session, tenant, monkeypatch):
    import importlib
    from amodb.apps.quality.service import _next_car_number
    from amodb.apps.quality.enums import CARProgram
    legacy = importlib.import_module("amodb.apps.quality.router")
    ctx, _ = tenant
    monkeypatch.setattr(numbering, "read_rules", lambda *args: {"audit_prefix": "QA", "car_prefix": "CAP", "reliability_car_prefix": "REL", "finding_prefix": "FIND", "sequence_digits": 4})
    assert legacy._audit_reference_family_for_amo(db_session, amo_id=ctx.amo_id) == "QA"
    audit_ref, _, _, _ = legacy._generate_audit_reference(db_session, amo_id=ctx.amo_id, target_date=date(2026, 1, 1), reference_family="QA")
    assert audit_ref == "QA/MO/26/0001"
    assert _next_car_number(db_session, CARProgram.QUALITY, ctx.amo_id).startswith("CAP/NUMBER/")
    audit = models.QMSAudit(amo_id=ctx.amo_id, domain=models.QMSDomain.AMO, kind=models.QMSAuditKind.INTERNAL, audit_ref=audit_ref, reference_family="QA", unit_code="MO", ref_year=26, ref_sequence=1, title="Numbered audit")
    db_session.add(audit); db_session.flush()
    assert legacy._next_audit_finding_ref(db_session, audit) == "QA/MO/26/0001-FIND-0001"


def test_audit_scope_and_settings_editors_share_prefix_configuration(db_session, tenant):
    from sqlalchemy import text
    import json
    ctx, _ = tenant
    db_session.execute(text("CREATE TABLE qms_settings (id TEXT PRIMARY KEY, amo_id TEXT, payload JSON, created_at TEXT, updated_at TEXT, updated_by TEXT, deleted_at TEXT)"))
    db_session.execute(text("INSERT INTO qms_settings (id, amo_id, payload, created_at) VALUES ('config', :amo, :value, '2026-10-26')"), {"amo": ctx.amo_id, "value": json.dumps({"numbering_rules": {"audit_prefix": "QA", "car_prefix": "CAP"}, "unrelated": "preserve"})})
    numbering.sync_workflow_prefix(db_session, ctx.amo_id, "QA", None)
    db_session.flush()
    assert db_session.query(models.QualityTenantWorkflowSettings).filter_by(amo_id=ctx.amo_id).one().audit_reference_family == "QA"
    numbering.sync_legacy_prefix(db_session, ctx.amo_id, "QAR2", None)
    assert numbering.read_rules(db_session, ctx.amo_id)["audit_prefix"] == "QAR2"
    stored = json.loads(db_session.execute(text("SELECT payload FROM qms_settings")).scalar_one())
    assert stored["unrelated"] == "preserve"
    with pytest.raises(HTTPException):
        numbering.sync_legacy_prefix(db_session, ctx.amo_id, "CAP", None)


@pytest.mark.parametrize("style, expected", [("YY", "26"), ("YYYY", "2026"), ("YYYY-MM", "2026-10"), ("YYYYMM", "202610"), ("YYMM", "2610")])
def test_server_date_format_changes_preserve_counter(db_session, tenant, style, expected):
    ctx, _ = tenant
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO") == "QA/MO/26/001"
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO", date_format=style) == f"QA/MO/{expected}/002"


def test_missing_counter_reconciles_other_date_formats(db_session, tenant):
    ctx, _ = tenant
    db_session.add(models.QMSAudit(amo_id=ctx.amo_id, domain=models.QMSDomain.AMO, kind=models.QMSAuditKind.INTERNAL, audit_ref="QA/MO/2026-09/012", reference_family="QA", unit_code="MO", ref_year=26, ref_sequence=12, title="Existing ISO reference"))
    db_session.flush()
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO", date_format="YYYY") == "QA/MO/2026/013"


def test_reset_rejects_stale_server_period_and_unapproved_scope(db_session, tenant):
    ctx, _ = tenant
    for updates, expected_status in [({"expected_period": "2025"}, 409), ({"expected_date_format": "YYYY"}, 409), ({"scope": "FAKE"}, 422), ({"month": 1}, 422)]:
        with pytest.raises(HTTPException) as error:
            router.reset_numbering_series(None, payload(**updates), ctx, db_session)
        assert error.value.status_code == expected_status


def test_annual_rollover_is_server_derived(db_session, tenant):
    ctx, _ = tenant
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO", issued_on=date(2026, 12, 31)) == "QA/MO/26/001"
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO", issued_on=date(2027, 1, 1), date_format="YYYY-MM") == "QA/MO/2027-01/001"


def test_audit_scope_preview_uses_server_date_and_configured_width(db_session, tenant, monkeypatch):
    import importlib
    legacy = importlib.import_module("amodb.apps.quality.router")
    monkeypatch.setattr(legacy, "reference_server_date", lambda: date(2026, 10, 26))
    ctx, _ = tenant
    scope = models.QMSAuditScope(amo_id=ctx.amo_id, code="MO", name="Maintenance", party_level="FIRST_PARTY", default_kind=models.QMSAuditKind.INTERNAL)
    db_session.add(scope); db_session.flush()
    value = legacy._scope_out(scope, reference_family="QA", reference_rules={"date_format": "YYYY-MM", "sequence_digits": 4}, next_sequence=3)
    assert value.next_reference == "QA/MO/2026-10/0003"
    assert value.reference_date_label == "2026-10"


def test_counter_reconciles_legacy_reference_metadata(db_session, tenant):
    ctx, _ = tenant
    db_session.add(models.QMSAudit(amo_id=ctx.amo_id, domain=models.QMSDomain.AMO, kind=models.QMSAuditKind.INTERNAL, audit_ref="LEGACY/REFERENCE", reference_family="QA", unit_code="MO", ref_year=26, ref_sequence=30, title="Legacy reference"))
    db_session.flush()
    assert numbering.reserve_reference(db_session, amo_id=ctx.amo_id, family="QA", unit="MO") == "QA/MO/26/031"
