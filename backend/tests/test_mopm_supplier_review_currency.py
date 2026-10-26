from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from amodb.apps.procurement import supplier_quality_control as gate
from amodb.apps.quality.provider_review_policy import review_assessment, apply_review_status


def today_utc():
    return datetime.now(timezone.utc).date()


@pytest.fixture
def reviewed_supplier(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    db = Session(engine)
    db.execute(text("""CREATE TABLE quality_external_provider_profiles (
        amo_id TEXT, supplier_id INTEGER, review_interval_days INTEGER,
        last_reviewed_on DATE, next_review_due_on DATE)"""))
    db.execute(text("INSERT INTO quality_external_provider_profiles VALUES ('tenant-a',7,365,:reviewed,NULL)"),{"reviewed":today_utc()})
    db.commit()
    supplier = SimpleNamespace(id=7,approved_at=today_utc()-timedelta(days=800))
    monkeypatch.setattr(gate.service,"assert_supplier_eligible",lambda *args,**kwargs:supplier)
    monkeypatch.setattr(gate,"_assert_required_contract_current",lambda *args,**kwargs:None)
    yield db,supplier
    db.close()
    engine.dispose()


def use(db, **kwargs):
    return gate.assert_supplier_usage_allowed(db,amo_id="tenant-a",supplier_id=7,categories={"MAINTENANCE"},**kwargs)


def test_current_quality_review_permits_supplier_use(reviewed_supplier):
    db,supplier = reviewed_supplier
    assert use(db) is supplier


@pytest.mark.parametrize("override",[False,True])
def test_annual_expiry_blocks_usage_even_with_legacy_long_interval_or_commercial_override(reviewed_supplier,override):
    db,_ = reviewed_supplier
    db.execute(text("UPDATE quality_external_provider_profiles SET last_reviewed_on=:reviewed,review_interval_days=3650,next_review_due_on=:due"),
        {"reviewed":today_utc()-timedelta(days=366),"due":today_utc()+timedelta(days=365)})
    with pytest.raises(HTTPException) as error:
        use(db,allow_controlled_override=override,override_reference="PO-EXCEPTION",override_reason="Commercial exception")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PROVIDER_REVIEW_OVERDUE"


def test_shorter_risk_review_remains_controlling(reviewed_supplier):
    db,_ = reviewed_supplier
    db.execute(text("UPDATE quality_external_provider_profiles SET last_reviewed_on=:reviewed,review_interval_days=90"),
        {"reviewed":today_utc()-timedelta(days=90)})
    with pytest.raises(HTTPException):
        use(db)


def test_future_or_missing_review_dates_cannot_extend_currency(reviewed_supplier):
    db,supplier = reviewed_supplier
    supplier.approved_at = None
    for reviewed in (None,today_utc()+timedelta(days=1)):
        db.execute(text("UPDATE quality_external_provider_profiles SET last_reviewed_on=:reviewed"),{"reviewed":reviewed})
        with pytest.raises(HTTPException) as error:
            use(db)
        assert error.value.detail["code"] == "PROVIDER_REVIEW_DATE_UNCONFIRMED"


def test_a_review_from_another_tenant_does_not_qualify_this_supplier(reviewed_supplier):
    db,_ = reviewed_supplier
    db.execute(text("UPDATE quality_external_provider_profiles SET amo_id='tenant-b'"))
    with pytest.raises(HTTPException) as error:
        use(db)
    assert error.value.detail["code"] == "PROVIDER_REVIEW_OVERDUE"


def test_display_and_gate_use_the_same_effective_deadline():
    today=date(2026,10,22)
    values=dict(approved_at=date(2024,1,1),last_reviewed_on=date(2025,10,21),
        review_interval_days=3650,next_review_due_on=date(2029,1,1))
    expected=review_assessment(**values,today=today)
    row=apply_review_status(dict(values),today=today)
    assert row["next_review_due_on"] == expected["due_on"] == date(2026,10,21)
    assert row["recorded_next_review_due_on"] == date(2029,1,1)
    assert row["review_due"] and not expected["current"]


def test_review_is_due_on_the_deadline_and_approval_anchors_legacy_profiles():
    today = date(2026, 10, 22)
    assessment = review_assessment(approved_at=today-timedelta(days=365), today=today)
    assert assessment == {"current": False, "code": "PROVIDER_REVIEW_OVERDUE", "due_on": today}


def test_initial_qualification_is_not_reported_as_an_overdue_periodic_review():
    row = apply_review_status({"status": "PROSPECTIVE"})
    assert row["review_due"] is False
    assert row["review_currency_code"] == "PROVIDER_REVIEW_DATE_UNCONFIRMED"


def test_unavailable_review_register_fails_closed(reviewed_supplier):
    db, _ = reviewed_supplier
    db.execute(text("DROP TABLE quality_external_provider_profiles"))
    with pytest.raises(HTTPException) as error:
        use(db)
    assert error.value.status_code == 503
