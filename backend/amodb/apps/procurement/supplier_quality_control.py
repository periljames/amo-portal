from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import models, service


_PROVIDER_PROFILE_TABLE = "quality_external_provider_profiles"
_PROVIDER_CONTRACT_TABLE = "quality_external_provider_contracts"


def _set_provider_tenant_context(db: Session, *, amo_id: str) -> None:
    """Set the tenant key used by FORCE-RLS provider governance tables."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT set_config('app.tenant_id', :amo_id, true)"),
        {"amo_id": str(amo_id)},
    )


def _assert_required_contract_current(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    allow_controlled_override: bool,
) -> None:
    """Fail closed when a governed provider requires a current contract.

    The Procurement supplier master remains authoritative for identity and QMS
    approval state.  The Quality provider profile is an additive governance
    layer.  When that profile makes a contract mandatory, Procurement may not
    award, order, dispatch or receive against the supplier without a currently
    active governed contract, unless the PO is already carrying the documented
    controlled override that must still pass Quality final approval.
    """
    inspector = inspect(db.get_bind())
    if not inspector.has_table(_PROVIDER_PROFILE_TABLE):
        # Backward compatibility for installations that have not yet introduced
        # provider contract governance: the canonical status/scope/hold gate
        # below remains mandatory.
        return

    _set_provider_tenant_context(db, amo_id=amo_id)
    contract_required = db.execute(
        text(
            """
            SELECT contract_required
            FROM quality_external_provider_profiles
            WHERE amo_id = :amo_id AND supplier_id = :supplier_id
            LIMIT 1
            """
        ),
        {"amo_id": str(amo_id), "supplier_id": supplier_id},
    ).scalar()
    if not bool(contract_required):
        return
    if allow_controlled_override:
        return

    if not inspector.has_table(_PROVIDER_CONTRACT_TABLE):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QMS requires a governed provider contract, but the contract register is unavailable.",
        )

    today = date.today()
    active_contract = db.execute(
        text(
            """
            SELECT 1
            FROM quality_external_provider_contracts
            WHERE amo_id = :amo_id
              AND supplier_id = :supplier_id
              AND status = 'ACTIVE'
              AND (effective_on IS NULL OR effective_on <= :today)
              AND (expires_on IS NULL OR expires_on >= :today)
            LIMIT 1
            """
        ),
        {"amo_id": str(amo_id), "supplier_id": supplier_id, "today": today},
    ).first()
    if not active_contract:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="QMS requires a current active contract before this external provider may be used.",
        )


def assert_supplier_usage_allowed(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    categories: Iterable[str],
    allow_controlled_override: bool = False,
    override_reference: Optional[str] = None,
    override_reason: Optional[str] = None,
) -> models.ProcurementSupplier:
    """Canonical cross-module gate for every supplier-use decision.

    QMS controls the usable supplier population through the shared Procurement
    supplier lifecycle state, approval scopes and Quality holds.  Provider
    contract governance adds a further mandatory-contract gate when configured.
    """
    supplier = service.assert_supplier_eligible(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        categories=categories,
        allow_controlled_override=allow_controlled_override,
        override_reference=override_reference,
        override_reason=override_reason,
    )
    _assert_required_contract_current(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        allow_controlled_override=allow_controlled_override,
    )
    return supplier


def assert_quote_award_allowed(db: Session, *, amo_id: str, quote_id: int) -> None:
    quote = (
        db.query(models.ProcurementQuote)
        .filter(
            models.ProcurementQuote.amo_id == amo_id,
            models.ProcurementQuote.id == quote_id,
        )
        .first()
    )
    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote was not found.")

    requisition = quote.rfq.requisition if quote.rfq else None
    categories = {
        str(line.item_type or ("PART" if line.part_number else "SERVICE")).strip().upper()
        for line in (requisition.lines if requisition else [])
    }
    if not categories:
        categories = {"GENERAL"}
    assert_supplier_usage_allowed(
        db,
        amo_id=amo_id,
        supplier_id=quote.supplier_id,
        categories=categories,
    )


def assert_purchase_order_allowed(db: Session, *, amo_id: str, po_id: int) -> None:
    po = (
        db.query(models.ProcurementPurchaseOrder)
        .filter(
            models.ProcurementPurchaseOrder.amo_id == amo_id,
            models.ProcurementPurchaseOrder.id == po_id,
        )
        .first()
    )
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order was not found.")

    allow_override = bool(po.override_reference and po.override_reason)
    assert_supplier_usage_allowed(
        db,
        amo_id=amo_id,
        supplier_id=po.supplier_id,
        categories={"PART" if line.part_number else "SERVICE" for line in po.lines},
        allow_controlled_override=allow_override,
        override_reference=po.override_reference,
        override_reason=po.override_reason,
    )
