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
    # Scoped internal Procurement check; external sessions cannot set this marker.
    db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))


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
    # Contract-mandatory maintenance cannot be bypassed by a Procurement PO override.
    # Overrides govern the commercial transaction, not the existence of the agreement.

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
            FROM quality_external_provider_contracts c
            JOIN manuals m ON m.id=c.controlled_document_id
            JOIN manual_tenants t ON t.id=m.tenant_id AND t.amo_id=c.amo_id
            JOIN manual_revisions r ON r.id=m.current_published_rev_id AND r.manual_id=m.id
              AND (r.id=c.controlled_document_revision OR r.rev_number=c.controlled_document_revision)
            JOIN external_partner_evidence_submissions s
              ON s.id=c.signed_evidence_submission_id AND s.amo_id=c.amo_id
              AND s.related_kind='CONTRACT' AND s.related_id=c.id
              AND s.status='ACCEPTED' AND s.sha256=r.source_sha256
              AND s.dms_evidence_asset_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM document_evidence_assets a
                JOIN document_retention_dispositions d
                  ON d.source_type='EVIDENCE_ASSET' AND d.source_id=a.id
                  AND d.tenant_id=a.tenant_id
                WHERE a.tenant_id=s.amo_id AND a.id=s.dms_evidence_asset_id
                  AND a.sha256=s.sha256 AND d.id=s.dms_retention_id
                  AND d.status!='DISPOSED'
              )
            JOIN external_tenant_providers p ON p.id=s.tenant_provider_id
              AND p.amo_id=c.amo_id AND p.supplier_id=c.supplier_id
            JOIN quality_external_provider_evidence q ON q.id=s.qms_evidence_id
              AND q.amo_id=c.amo_id AND q.supplier_id=c.supplier_id
              AND q.status='VERIFIED'
              AND (q.valid_until IS NULL OR q.valid_until>=:today)
            WHERE c.amo_id = :amo_id AND c.supplier_id = :supplier_id
              AND c.status = 'ACTIVE'
              AND (c.effective_on IS NULL OR c.effective_on <= :today)
              AND (c.expires_on IS NULL OR c.expires_on >= :today)
              AND r.status_enum='PUBLISHED' AND r.published_at IS NOT NULL
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



def assert_provider_restrictions_allowed(
    db: Session, *, amo_id: str, supplier_id: int, categories: Iterable[str],
    site_code: str | None = None, product_family: str | None = None,
    capability: str | None = None, contracted_function: str | None = None,
    contract_id: str | None = None,
) -> None:
    """Transactional fail-closed Quality restrictions; no override bypass."""
    if not inspect(db.get_bind()).has_table("quality_provider_restrictions"):
        return
    _set_provider_tenant_context(db, amo_id=amo_id)
    restrictions = db.execute(text("""
        SELECT dimension,target_key FROM quality_provider_restrictions
        WHERE amo_id=:amo AND supplier_id=:supplier AND status='ACTIVE'
        AND effective_on<=CURRENT_DATE
        AND (ends_on IS NULL OR ends_on>=CURRENT_DATE)
    """), {"amo":str(amo_id),"supplier":supplier_id}).mappings().all()
    category_set={str(x).upper() for x in categories}
    fields={"SITE":site_code, "PRODUCT_FAMILY":product_family,
            "CAPABILITY":capability,"FUNCTION":contracted_function,
            "CONTRACT":contract_id}
    for restriction in restrictions:
        dim=restriction["dimension"];target=str(restriction["target_key"])
        if dim=="ORGANIZATION":
            blocked=True
        elif dim=="CATEGORY":
            blocked=not category_set or target=="*" or target.upper() in category_set
        else:
            actual=fields.get(dim)
            blocked=actual is None or target=="*" or str(actual).casefold()==target.casefold()
        if blocked:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail={
                "code":"PROVIDER_QUALITY_RESTRICTION","dimension":dim,"target":target,
                "message":"Active QMS restriction prohibits this supplier-use transition",
            })


def assert_supplier_usage_allowed(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    categories: Iterable[str],
    allow_controlled_override: bool = False,
    override_reference: Optional[str] = None,
    override_reason: Optional[str] = None,
    site_code: Optional[str] = None,
    product_family: Optional[str] = None,
    capability: Optional[str] = None,
    contracted_function: Optional[str] = None,
    contract_id: Optional[str] = None,
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
    assert_provider_restrictions_allowed(
        db, amo_id=amo_id, supplier_id=supplier_id, categories=categories,
        site_code=site_code, product_family=product_family,
        capability=capability, contracted_function=contracted_function,
        contract_id=contract_id,
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

    # Supplier revisions and withdrawal stay visible in the canonical register,
    # but an obsolete or withdrawn external quote cannot be awarded.
    if inspect(db.get_bind()).has_table("external_procurement_quotes"):
        _set_provider_tenant_context(db, amo_id=amo_id)
        ext = db.execute(text("""SELECT status FROM external_procurement_quotes
          WHERE amo_id=:amo AND supplier_id=:supplier AND canonical_quote_id=:quote"""),
          {"amo":amo_id,"supplier":quote.supplier_id,"quote":quote_id}).mappings().first()
        if ext and ext["status"]!="SUBMITTED":
            raise HTTPException(status_code=409,
                detail="Withdrawn or superseded external quotation cannot be awarded")
        if ext and (quote.valid_until is None or quote.valid_until<date.today()):
            raise HTTPException(status_code=409,
                detail="External quotation validity has expired; obtain a current controlled revision")
        if ext and any(not line.is_technically_compliant for line in quote.lines):
            raise HTTPException(status_code=409,
                detail="Proposed alternate/deviation needs an approved technical decision before award")

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
