from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
PROCUREMENT = BACKEND / "amodb" / "apps" / "procurement"
FRONTEND = BACKEND.parent / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_procurement_python_sources_parse() -> None:
    for path in [
        PROCUREMENT / "models.py",
        PROCUREMENT / "schemas.py",
        PROCUREMENT / "service.py",
        PROCUREMENT / "router.py",
        BACKEND / "amodb" / "alembic" / "versions" / "procurement_20260803_full_domain.py",
    ]:
        ast.parse(_read(path), filename=str(path))


def test_receiving_is_quarantined_until_quality_release() -> None:
    models = _read(PROCUREMENT / "models.py")
    service = _read(PROCUREMENT / "service.py")
    inventory_schemas = _read(BACKEND / "amodb" / "apps" / "inventory" / "schemas.py")
    inventory_router = _read(BACKEND / "amodb" / "apps" / "inventory" / "router.py")

    assert 'default=ReceiptStatus.QUARANTINED' in models
    assert 'status=models.ReceiptStatus.QUARANTINED' in service
    assert 'condition=inventory_models.InventoryConditionEnum.SERVICEABLE' in service
    assert service.index('condition=inventory_models.InventoryConditionEnum.SERVICEABLE') > service.index('def release_receipt(')
    assert 'models.InventoryConditionEnum.QUARANTINE' in inventory_schemas
    assert inventory_router.count('condition = models.InventoryConditionEnum.QUARANTINE') >= 2


def test_segregation_of_duties_is_backend_enforced() -> None:
    service = _read(PROCUREMENT / "service.py")
    assert 'A requester cannot approve their own requisition.' in service
    assert 'The requester/creator cannot approve this purchase order.' in service
    assert 'The receiver cannot perform the independent receiving inspection.' in service
    assert 'The receiver cannot release the same receipt.' in service


def test_supplier_quality_gate_covers_new_and_legacy_orders() -> None:
    service = _read(PROCUREMENT / "service.py")
    inventory_router = _read(BACKEND / "amodb" / "apps" / "inventory" / "router.py")

    assert 'def assert_supplier_eligible(' in service
    assert 'def assert_legacy_purchase_order_eligible(' in service
    assert 'procurement_service.assert_legacy_purchase_order_eligible' in inventory_router
    assert 'Supplier approval scope does not cover every purchase-order category.' in service
    assert 'Supplier has an active Quality hold.' in service


def test_module_exposes_manageable_department_routes() -> None:
    router = _read(PROCUREMENT / "router.py")
    frontend_router = _read(FRONTEND / "router.tsx")
    module = _read(FRONTEND / "pages" / "procurement" / "ProcurementModule.tsx")

    assert 'prefix="/api/maintenance/{amo_code}/procurement"' in router
    for endpoint in [
        '"/dashboard"',
        '"/reference-data"',
        '"/requisitions"',
        '"/rfqs"',
        '"/quotes"',
        '"/purchase-orders"',
        '"/receipts"',
        '"/suppliers"',
        '"/quality-holds"',
        '"/finance/three-way-match"',
    ]:
        assert endpoint in router

    assert 'parts[2] === "procurement" || parts[2] === "stores"' in frontend_router
    for label in ["Home", "Requests", "Sourcing", "Orders", "Receiving", "Suppliers", "Control"]:
        assert f'label: "{label}"' in module


def test_cross_module_linkage_is_explicit() -> None:
    models = _read(PROCUREMENT / "models.py")
    module = _read(FRONTEND / "pages" / "procurement" / "ProcurementModule.tsx")

    for foreign_table in [
        'ForeignKey("vendors.id"',
        'ForeignKey("inventory_parts.id"',
        'ForeignKey("inventory_locations.id"',
        'ForeignKey("work_orders.id"',
        'ForeignKey("task_cards.id"',
        'ForeignKey("aircraft.serial_number"',
        'ForeignKey("inventory_movement_ledger.id"',
    ]:
        assert foreign_table in models

    for workspace in ["planning", "production", "maintenance", "quality", "finance"]:
        assert workspace in module
