from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from amodb.apps.accounts import models as account_models

from . import models, schemas, service, supplier_quality_control


router = APIRouter(
    prefix="/api/maintenance/{amo_code}/procurement",
    tags=["procurement"],
    dependencies=[Depends(require_module("finance_inventory"))],
)


REQUEST_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PROCUREMENT_OFFICER,
    account_models.AccountRole.STORES_MANAGER,
    account_models.AccountRole.STOREKEEPER,
    account_models.AccountRole.STORES,
    account_models.AccountRole.PLANNING_ENGINEER,
    account_models.AccountRole.PRODUCTION_ENGINEER,
    account_models.AccountRole.CERTIFYING_ENGINEER,
    account_models.AccountRole.CERTIFYING_TECHNICIAN,
)
PROCUREMENT_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PROCUREMENT_OFFICER,
    account_models.AccountRole.STORES_MANAGER,
)
TECHNICAL_APPROVAL_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PLANNING_ENGINEER,
    account_models.AccountRole.PRODUCTION_ENGINEER,
    account_models.AccountRole.CERTIFYING_ENGINEER,
)
FINANCE_APPROVAL_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.FINANCE_MANAGER,
    account_models.AccountRole.ACCOUNTS_OFFICER,
)
QUALITY_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.QUALITY_MANAGER,
    account_models.AccountRole.QUALITY_INSPECTOR,
)
RECEIVING_ROLES = (
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.STORES_MANAGER,
    account_models.AccountRole.STOREKEEPER,
    account_models.AccountRole.STORES,
    account_models.AccountRole.QUALITY_INSPECTOR,
)


def _tenant(
    db: Session,
    *,
    amo_code: str,
    current_user: account_models.User,
) -> str:
    return service.resolve_tenant_amo_id(db, amo_code=amo_code, current_user=current_user)


def _commit_refresh(db: Session, record):
    db.commit()
    db.refresh(record)
    return record


@router.get("/reference-data", response_model=schemas.ProcurementReferenceData)
def procurement_reference_data(
    amo_code: str,
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.reference_data(db, amo_id=amo_id, limit=limit)


@router.get("/dashboard", response_model=schemas.DashboardResponse)
def procurement_dashboard(
    amo_code: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.dashboard(db, amo_id=amo_id)


@router.get("/suppliers", response_model=List[schemas.SupplierRead])
def suppliers_list(
    amo_code: str,
    status_filter: Optional[models.SupplierLifecycleStatus] = Query(None, alias="status"),
    q: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_suppliers(db, amo_id=amo_id, status_filter=status_filter, q=q, limit=limit)


@router.post("/suppliers", response_model=schemas.SupplierRead, status_code=status.HTTP_201_CREATED)
def supplier_create(
    amo_code: str,
    payload: schemas.SupplierCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    supplier = service.create_supplier(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, supplier)


@router.patch("/suppliers/{supplier_id}", response_model=schemas.SupplierRead)
def supplier_update(
    amo_code: str,
    supplier_id: int,
    payload: schemas.SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    supplier = service.update_supplier(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, supplier)


@router.post(
    "/suppliers/{supplier_id}/approval-scopes",
    response_model=schemas.ApprovalScopeRead,
    status_code=status.HTTP_201_CREATED,
)
def supplier_scope_create(
    amo_code: str,
    supplier_id: int,
    payload: schemas.ApprovalScopeCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    scope = service.add_supplier_scope(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, scope)


@router.post("/suppliers/{supplier_id}/decision", response_model=schemas.SupplierRead)
def supplier_decision(
    amo_code: str,
    supplier_id: int,
    payload: schemas.SupplierDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    supplier = service.decide_supplier(
        db,
        amo_id=amo_id,
        supplier_id=supplier_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, supplier)


@router.get("/requisitions", response_model=List[schemas.RequisitionRead])
def requisitions_list(
    amo_code: str,
    status_filter: Optional[models.RequisitionStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_requisitions(db, amo_id=amo_id, status_filter=status_filter, limit=limit)


@router.post("/requisitions", response_model=schemas.RequisitionRead, status_code=status.HTTP_201_CREATED)
def requisition_create(
    amo_code: str,
    payload: schemas.RequisitionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*REQUEST_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    requisition = service.create_requisition(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, requisition)


@router.post("/requisitions/{requisition_id}/transition", response_model=schemas.RequisitionRead)
def requisition_transition(
    amo_code: str,
    requisition_id: int,
    payload: schemas.RequisitionTransition,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*REQUEST_ROLES, *FINANCE_APPROVAL_ROLES)),
):
    if payload.action == "TECHNICAL_APPROVE" and current_user.role not in TECHNICAL_APPROVAL_ROLES and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Technical approval role is required.")
    if payload.action == "BUDGET_APPROVE" and current_user.role not in FINANCE_APPROVAL_ROLES and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Finance approval role is required.")
    if payload.action == "APPROVE" and current_user.role not in PROCUREMENT_ROLES and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Procurement approval role is required.")
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    requisition = service.transition_requisition(
        db,
        amo_id=amo_id,
        requisition_id=requisition_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, requisition)


@router.get("/rfqs", response_model=List[schemas.RFQRead])
def rfqs_list(
    amo_code: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_rfqs(db, amo_id=amo_id, limit=limit)


@router.post("/rfqs", response_model=schemas.RFQRead, status_code=status.HTTP_201_CREATED)
def rfq_create(
    amo_code: str,
    payload: schemas.RFQCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    rfq = service.create_rfq(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, rfq)


@router.get("/quotes", response_model=List[schemas.QuoteRead])
def quotes_list(
    amo_code: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_quotes(db, amo_id=amo_id, limit=limit)


@router.post("/quotes", response_model=schemas.QuoteRead, status_code=status.HTTP_201_CREATED)
def quote_create(
    amo_code: str,
    payload: schemas.QuoteCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    quote = service.create_quote(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, quote)


@router.post("/quotes/{quote_id}/evaluate", response_model=schemas.QuoteRead)
def quote_evaluate(
    amo_code: str,
    quote_id: int,
    payload: schemas.QuoteEvaluate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES, *TECHNICAL_APPROVAL_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    if payload.status == models.QuoteStatus.AWARDED:
        supplier_quality_control.assert_quote_award_allowed(db, amo_id=amo_id, quote_id=quote_id)
    quote = service.evaluate_quote(
        db,
        amo_id=amo_id,
        quote_id=quote_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, quote)


@router.get("/purchase-orders", response_model=List[schemas.PurchaseOrderRead])
def purchase_orders_list(
    amo_code: str,
    status_filter: Optional[models.PurchaseOrderStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_purchase_orders(db, amo_id=amo_id, status_filter=status_filter, limit=limit)


@router.post("/purchase-orders", response_model=schemas.PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
def purchase_order_create(
    amo_code: str,
    payload: schemas.PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    supplier_quality_control.assert_supplier_usage_allowed(
        db,
        amo_id=amo_id,
        supplier_id=payload.supplier_id,
        categories={"PART" if line.part_number else "SERVICE" for line in payload.lines},
        allow_controlled_override=bool(payload.override_reference and payload.override_reason),
        override_reference=payload.override_reference,
        override_reason=payload.override_reason,
    )
    po = service.create_purchase_order(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, po)


@router.post("/purchase-orders/{po_id}/approve", response_model=schemas.PurchaseOrderRead)
def purchase_order_approve(
    amo_code: str,
    po_id: int,
    payload: schemas.PurchaseOrderApproval,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*TECHNICAL_APPROVAL_ROLES, *FINANCE_APPROVAL_ROLES, *PROCUREMENT_ROLES, *QUALITY_ROLES)
    ),
):
    stage_roles = {
        "TECHNICAL": TECHNICAL_APPROVAL_ROLES,
        "BUDGET": FINANCE_APPROVAL_ROLES,
        "PROCUREMENT": PROCUREMENT_ROLES,
        "QUALITY": QUALITY_ROLES,
        "FINAL": QUALITY_ROLES,
    }
    if current_user.role not in stage_roles[payload.stage] and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail=f"{payload.stage.title()} approval role is required.")
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    if payload.stage in {"QUALITY", "FINAL"}:
        supplier_quality_control.assert_purchase_order_allowed(db, amo_id=amo_id, po_id=po_id)
    po = service.approve_purchase_order(
        db,
        amo_id=amo_id,
        po_id=po_id,
        payload=payload,
        actor_user_id=current_user.id,
        actor_is_quality=current_user.role in QUALITY_ROLES or current_user.is_superuser,
    )
    return _commit_refresh(db, po)


@router.post("/purchase-orders/{po_id}/send", response_model=schemas.PurchaseOrderRead)
def purchase_order_send(
    amo_code: str,
    po_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    supplier_quality_control.assert_purchase_order_allowed(db, amo_id=amo_id, po_id=po_id)
    po = service.send_purchase_order(db, amo_id=amo_id, po_id=po_id, actor_user_id=current_user.id)
    return _commit_refresh(db, po)


@router.post("/purchase-orders/{po_id}/acknowledge", response_model=schemas.PurchaseOrderRead)
def purchase_order_acknowledge(
    amo_code: str,
    po_id: int,
    payload: schemas.PurchaseOrderAcknowledge,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROCUREMENT_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    po = service.acknowledge_purchase_order(
        db,
        amo_id=amo_id,
        po_id=po_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, po)


@router.get("/receipts", response_model=List[schemas.ReceiptRead])
def receipts_list(
    amo_code: str,
    status_filter: Optional[models.ReceiptStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_receipts(db, amo_id=amo_id, status_filter=status_filter, limit=limit)


@router.post("/receipts", response_model=schemas.ReceiptRead, status_code=status.HTTP_201_CREATED)
def receipt_create(
    amo_code: str,
    payload: schemas.ReceiptCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*RECEIVING_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    po = (
        db.query(models.ProcurementPurchaseOrder)
        .filter(
            models.ProcurementPurchaseOrder.amo_id == amo_id,
            models.ProcurementPurchaseOrder.id == payload.purchase_order_id,
        )
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order was not found.")
    supplier_quality_control.assert_purchase_order_allowed(db, amo_id=amo_id, po_id=po.id)
    receipt = service.create_receipt(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, receipt)


@router.post("/receipts/{receipt_id}/inspect", response_model=schemas.ReceiptRead)
def receipt_inspect(
    amo_code: str,
    receipt_id: int,
    payload: schemas.InspectionCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    receipt = service.inspect_receipt(
        db,
        amo_id=amo_id,
        receipt_id=receipt_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, receipt)


@router.post("/receipts/{receipt_id}/release", response_model=schemas.ReceiptRead)
def receipt_release(
    amo_code: str,
    receipt_id: int,
    payload: schemas.ReceiptRelease,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    receipt = service.release_receipt(
        db,
        amo_id=amo_id,
        receipt_id=receipt_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, receipt)


@router.get("/quality-holds", response_model=List[schemas.QualityHoldRead])
def quality_holds_list(
    amo_code: str,
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    return service.list_quality_holds(db, amo_id=amo_id, active_only=active_only, limit=limit)


@router.post("/quality-holds", response_model=schemas.QualityHoldRead, status_code=status.HTTP_201_CREATED)
def quality_hold_create(
    amo_code: str,
    payload: schemas.QualityHoldCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    hold = service.create_quality_hold(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, hold)


@router.post("/quality-holds/{hold_id}/release", response_model=schemas.QualityHoldRead)
def quality_hold_release(
    amo_code: str,
    hold_id: int,
    payload: schemas.QualityHoldRelease,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*QUALITY_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    hold = service.release_quality_hold(
        db,
        amo_id=amo_id,
        hold_id=hold_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, hold)


@router.post("/finance/three-way-match", response_model=schemas.InvoiceMatchRead)
def invoice_match_create(
    amo_code: str,
    payload: schemas.InvoiceMatchCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*FINANCE_APPROVAL_ROLES)),
):
    amo_id = _tenant(db, amo_code=amo_code, current_user=current_user)
    match = service.create_invoice_match(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    return _commit_refresh(db, match)
