from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from amodb.apps.procurement import supplier_quality_control


BACKEND = Path(__file__).resolve().parents[1]
PROCUREMENT = BACKEND / "amodb" / "apps" / "procurement"
QUALITY = BACKEND / "amodb" / "apps" / "quality"


def _provider_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE quality_external_provider_profiles (
                id TEXT PRIMARY KEY,
                amo_id TEXT NOT NULL,
                supplier_id INTEGER NOT NULL,
                contract_required BOOLEAN NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE quality_external_provider_contracts (
                id TEXT PRIMARY KEY,
                amo_id TEXT NOT NULL,
                supplier_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                effective_on DATE,
                expires_on DATE
            )
        """))
        connection.execute(
            text("""
                INSERT INTO quality_external_provider_profiles
                    (id, amo_id, supplier_id, contract_required)
                VALUES ('profile-1', 'amo-1', 7, 1)
            """)
        )
    return Session(engine)


def _stub_base_supplier_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        supplier_quality_control.service,
        "assert_supplier_eligible",
        lambda *args, **kwargs: object(),
    )


def test_required_provider_contract_blocks_supplier_use(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _provider_db()
    _stub_base_supplier_gate(monkeypatch)
    try:
        with pytest.raises(HTTPException) as exc:
            supplier_quality_control.assert_supplier_usage_allowed(
                db,
                amo_id="amo-1",
                supplier_id=7,
                categories={"PART"},
            )
        assert exc.value.status_code == 409
        assert "current active contract" in str(exc.value.detail)
    finally:
        db.close()


def test_current_provider_contract_allows_supplier_use(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _provider_db()
    _stub_base_supplier_gate(monkeypatch)
    today = date.today()
    try:
        db.execute(
            text("""
                INSERT INTO quality_external_provider_contracts
                    (id, amo_id, supplier_id, status, effective_on, expires_on)
                VALUES ('contract-1', 'amo-1', 7, 'ACTIVE', :effective_on, :expires_on)
            """),
            {"effective_on": today - timedelta(days=30), "expires_on": today + timedelta(days=30)},
        )
        db.commit()
        supplier_quality_control.assert_supplier_usage_allowed(
            db,
            amo_id="amo-1",
            supplier_id=7,
            categories={"PART"},
        )
    finally:
        db.close()


def test_expired_provider_contract_blocks_supplier_use(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _provider_db()
    _stub_base_supplier_gate(monkeypatch)
    today = date.today()
    try:
        db.execute(
            text("""
                INSERT INTO quality_external_provider_contracts
                    (id, amo_id, supplier_id, status, effective_on, expires_on)
                VALUES ('contract-1', 'amo-1', 7, 'ACTIVE', :effective_on, :expires_on)
            """),
            {"effective_on": today - timedelta(days=60), "expires_on": today - timedelta(days=1)},
        )
        db.commit()
        with pytest.raises(HTTPException) as exc:
            supplier_quality_control.assert_supplier_usage_allowed(
                db,
                amo_id="amo-1",
                supplier_id=7,
                categories={"PART"},
            )
        assert exc.value.status_code == 409
    finally:
        db.close()


def test_documented_quality_override_can_cross_contract_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _provider_db()
    _stub_base_supplier_gate(monkeypatch)
    try:
        supplier_quality_control.assert_supplier_usage_allowed(
            db,
            amo_id="amo-1",
            supplier_id=7,
            categories={"PART"},
            allow_controlled_override=True,
            override_reference="QMS-OVR-2026-001",
            override_reason="Aircraft-on-ground controlled exception approved through the PO Quality gate.",
        )
    finally:
        db.close()


def test_procurement_use_boundaries_are_qms_gated() -> None:
    router = (PROCUREMENT / "router.py").read_text(encoding="utf-8")
    service = (PROCUREMENT / "service.py").read_text(encoding="utf-8")
    provider = (QUALITY / "provider_governance_router.py").read_text(encoding="utf-8")

    assert "payload.status == models.QuoteStatus.AWARDED" in router
    assert "supplier_quality_control.assert_quote_award_allowed" in router
    assert "supplier_quality_control.assert_supplier_usage_allowed" in router
    assert router.count("supplier_quality_control.assert_purchase_order_allowed") >= 3

    # The pre-existing canonical gate remains the foundation: QMS lifecycle
    # status, active approval scope, and Quality holds all block supplier use.
    assert "Supplier has an active Quality hold." in service
    assert "Supplier is not eligible for award" in service
    assert "Supplier approval scope does not cover every purchase-order category." in service

    # Quality owns the lifecycle decision and approval scope mutations in the
    # legacy Procurement API, while the modern provider workspace requires the
    # QMS supplier-management permission and writes the same supplier master.
    assert 'current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES))' in router
    assert 'assert_quality_permission(db, ctx, "qms.supplier.manage")' in provider
    assert "UPDATE procurement_suppliers" in provider
    assert "FROM procurement_suppliers s" in provider


def test_qms_controls_contractors_and_subcontractors_not_only_part_suppliers() -> None:
    provider = (QUALITY / "provider_governance_router.py").read_text(encoding="utf-8")
    migration = (
        BACKEND / "amodb" / "alembic" / "versions" / "quality_20260820_external_provider_governance.py"
    ).read_text(encoding="utf-8")

    for kind in ["SUPPLIER", "CONTRACTOR", "SUBCONTRACTOR", "SERVICE_PROVIDER"]:
        assert f'"{kind}"' in provider
        assert kind in migration
    assert "contract_required" in provider
    assert "quality_external_provider_contracts" in provider
    assert "quality_external_provider_evidence" in provider
