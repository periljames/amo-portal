from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
PROCUREMENT = BACKEND / "amodb" / "apps" / "procurement"
FRONTEND = BACKEND.parent / "frontend" / "src"
DOC = BACKEND.parent / "docs" / "procurement-module.md"


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
    assert inventory_router.count('condition = models.InventoryConditionEnum.QUARANTINE') >= 1


def test_segregation_of_duties_is_backend_enforced() -> None:
    service = _read(PROCUREMENT / "service.py")
    assert 'A requester cannot approve their own requisition.' in service
    assert 'The requester/creator cannot approve this purchase order.' in service
    assert 'The receiver cannot perform the independent receiving inspection.' in service
    assert 'The receiver cannot release the same receipt.' in service


def test_supplier_quality_gate_is_canonical() -> None:
    service = _read(PROCUREMENT / "service.py")
    inventory_router = _read(BACKEND / "amodb" / "apps" / "inventory" / "router.py")
    models = _read(PROCUREMENT / "models.py")

    assert 'def assert_supplier_eligible(' in service
    assert 'Supplier approval scope does not cover every purchase-order category.' in service
    assert 'Supplier has an active Quality hold.' in service
    assert 'assert_legacy_purchase_order_eligible' not in service
    assert 'legacy_purchase_order_id' not in models
    assert '/purchasing/' not in inventory_router


def test_module_exposes_only_canonical_department_routes() -> None:
    router = _read(PROCUREMENT / "router.py")
    frontend_router = _read(FRONTEND / "router.tsx")
    module = _read(FRONTEND / "pages" / "procurement" / "ProcurementModule.tsx")
    shared_ui = _read(FRONTEND / "pages" / "procurement" / "procurementUiShared.tsx")
    department_access = _read(FRONTEND / "utils" / "departmentAccess.ts")

    assert 'prefix="/api/maintenance/{amo_code}/procurement"' in router
    for endpoint in [
        '"/dashboard"', '"/reference-data"', '"/requisitions"', '"/rfqs"',
        '"/quotes"', '"/purchase-orders"', '"/receipts"', '"/suppliers"',
        '"/quality-holds"', '"/finance/three-way-match"',
    ]:
        assert endpoint in router

    assert 'parts[2] === "procurement"' in frontend_router
    assert 'parts[2] === "procurement" || parts[2] === "stores"' not in frontend_router
    assert 'part === "stores"' not in module
    assert 'activeDepartment="procurement"' in module
    assert '{ id: "procurement", label: "Procurement & Supply Chain" }' in department_access
    assert '{ id: "stores", label: "Stores & Inventory" }' in department_access
    assert 'case "PROCUREMENT_OFFICER":' in department_access
    assert 'return "procurement"' in department_access
    for label in ["Command", "Requests", "Sourcing", "Orders", "Receiving", "Suppliers", "Quality Control", "Documents"]:
        assert f'label: "{label}"' in shared_ui


def test_cross_module_linkage_is_explicit() -> None:
    models = _read(PROCUREMENT / "models.py")
    module = _read(FRONTEND / "pages" / "procurement" / "ProcurementModule.tsx").lower()
    documentation = _read(DOC).lower()

    for foreign_table in [
        'ForeignKey("vendors.id"', 'ForeignKey("inventory_parts.id"',
        'ForeignKey("inventory_locations.id"', 'ForeignKey("work_orders.id"',
        'ForeignKey("task_cards.id"', 'ForeignKey("aircraft.serial_number"',
        'ForeignKey("inventory_movement_ledger.id"',
    ]:
        assert foreign_table in models

    for workspace in ["planning", "production", "maintenance", "quality", "finance", "documents"]:
        assert workspace in module or workspace in documentation


def test_documented_scope_is_complete() -> None:
    doc = _read(DOC)
    assert 'Stores remains a separate inventory and custody department' in doc
    assert 'compatibility alias' not in doc
    assert 'deprecated' not in doc
    assert doc.count('- [x]') >= 13
