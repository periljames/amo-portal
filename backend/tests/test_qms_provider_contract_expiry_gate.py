from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "amodb" / "apps" / "procurement" / "supplier_quality_control.py"
ROUTER = ROOT / "amodb" / "apps" / "procurement" / "router.py"


def test_expired_mandatory_contract_cannot_be_used_after_prior_approval() -> None:
    gate = GATE.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")

    assert "expires_on IS NULL OR expires_on >= :today" in gate
    assert "status = 'ACTIVE'" in gate
    assert "QMS requires a current active contract before this external provider may be used." in gate
    assert "purchase_order_send" in router
    assert "receipt_create" in router
    assert router.count("supplier_quality_control.assert_purchase_order_allowed") >= 3
