from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.finance import models as finance_models
from amodb.apps.inventory import models as inventory_models
from amodb.apps.inventory import schemas as inventory_schemas
from amodb.apps.inventory import services as inventory_services

from . import models, schemas


def resolve_tenant_amo_id(
    db: Session,
    *,
    amo_code: str,
    current_user: account_models.User,
) -> str:
    amo = (
        db.query(account_models.AMO)
        .filter(
            or_(
                func.lower(account_models.AMO.amo_code) == amo_code.strip().lower(),
                func.lower(account_models.AMO.login_slug) == amo_code.strip().lower(),
            )
        )
        .first()
    )
    if not amo:
        raise HTTPException(status_code=404, detail="Tenant was not found.")

    user_amo_id = getattr(current_user, "effective_amo_id", None) or current_user.amo_id
    if not current_user.is_superuser and str(user_amo_id) != str(amo.id):
        raise HTTPException(status_code=403, detail="Tenant access denied.")
    return str(amo.id)


def _event(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: Optional[str],
    detail: Optional[dict] = None,
) -> None:
    event = models.ProcurementEvent(
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        actor_user_id=actor_user_id,
        detail=detail or {},
    )
    db.add(event)
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor_user_id=actor_user_id,
            after_json=detail or {},
        ),
    )


def reference_data(db: Session, *, amo_id: str, limit: int = 500) -> schemas.ProcurementReferenceData:
    bounded = min(max(limit, 1), 1000)
    locations = (
        db.query(inventory_models.InventoryLocation)
        .filter(
            inventory_models.InventoryLocation.amo_id == amo_id,
            inventory_models.InventoryLocation.is_active.is_(True),
        )
        .order_by(inventory_models.InventoryLocation.code.asc())
        .limit(bounded)
        .all()
    )
    parts = (
        db.query(inventory_models.InventoryPart)
        .filter(inventory_models.InventoryPart.amo_id == amo_id)
        .order_by(inventory_models.InventoryPart.part_number.asc())
        .limit(bounded)
        .all()
    )
    vendors = (
        db.query(finance_models.Vendor)
        .filter(finance_models.Vendor.amo_id == amo_id)
        .order_by(finance_models.Vendor.name.asc())
        .limit(bounded)
        .all()
    )
    return schemas.ProcurementReferenceData(locations=locations, parts=parts, vendors=vendors)


def _get_supplier(db: Session, *, amo_id: str, supplier_id: int) -> models.ProcurementSupplier:
    supplier = (
        db.query(models.ProcurementSupplier)
        .filter(
            models.ProcurementSupplier.amo_id == amo_id,
            models.ProcurementSupplier.id == supplier_id,
        )
        .first()
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier was not found.")
    return supplier


def _active_holds(
    db: Session,
    *,
    amo_id: str,
    targets: Iterable[tuple[str, str]],
) -> list[models.ProcurementQualityHold]:
    clauses = [
        (
            models.ProcurementQualityHold.target_type == target_type,
            models.ProcurementQualityHold.target_id == str(target_id),
        )
        for target_type, target_id in targets
    ]
    if not clauses:
        return []
    return (
        db.query(models.ProcurementQualityHold)
        .filter(
            models.ProcurementQualityHold.amo_id == amo_id,
            models.ProcurementQualityHold.status == models.QualityHoldStatus.ACTIVE,
            or_(*[a & b for a, b in clauses]),
        )
        .all()
    )


def assert_supplier_eligible(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    categories: Iterable[str],
    allow_controlled_override: bool = False,
    override_reference: Optional[str] = None,
    override_reason: Optional[str] = None,
) -> models.ProcurementSupplier:
    supplier = _get_supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    blocking_holds = _active_holds(
        db,
        amo_id=amo_id,
        targets=[("SUPPLIER", str(supplier.id))],
    )
    if blocking_holds and not allow_controlled_override:
        raise HTTPException(status_code=409, detail="Supplier has an active Quality hold.")

    permitted_statuses = {
        models.SupplierLifecycleStatus.APPROVED,
        models.SupplierLifecycleStatus.CONDITIONALLY_APPROVED,
    }
    if supplier.status not in permitted_statuses or not supplier.is_active:
        if not allow_controlled_override:
            raise HTTPException(
                status_code=409,
                detail=f"Supplier is not eligible for award; current status is {supplier.status.value}.",
            )

    today = date.today()
    requested = {str(value or "GENERAL").strip().upper() for value in categories}
    scopes = (
        db.query(models.SupplierApprovalScope)
        .filter(
            models.SupplierApprovalScope.amo_id == amo_id,
            models.SupplierApprovalScope.supplier_id == supplier.id,
            models.SupplierApprovalScope.status == models.ApprovalScopeStatus.ACTIVE,
            or_(
                models.SupplierApprovalScope.effective_on.is_(None),
                models.SupplierApprovalScope.effective_on <= today,
            ),
            or_(
                models.SupplierApprovalScope.expires_on.is_(None),
                models.SupplierApprovalScope.expires_on >= today,
            ),
        )
        .all()
    )
    covered = {
        scope.category.strip().upper()
        for scope in scopes
    }
    scope_ok = "ALL" in covered or requested.issubset(covered)
    if not scope_ok and not allow_controlled_override:
        raise HTTPException(
            status_code=409,
            detail="Supplier approval scope does not cover every purchase-order category.",
        )

    if allow_controlled_override and (not override_reference or not override_reason):
        raise HTTPException(
            status_code=400,
            detail="A controlled override requires both override_reference and override_reason.",
        )
    return supplier


def list_suppliers(
    db: Session,
    *,
    amo_id: str,
    status_filter: Optional[models.SupplierLifecycleStatus] = None,
    q: Optional[str] = None,
    limit: int = 100,
) -> list[models.ProcurementSupplier]:
    query = db.query(models.ProcurementSupplier).filter(models.ProcurementSupplier.amo_id == amo_id)
    if status_filter:
        query = query.filter(models.ProcurementSupplier.status == status_filter)
    if q:
        value = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.ProcurementSupplier.supplier_code.ilike(value),
                models.ProcurementSupplier.legal_name.ilike(value),
                models.ProcurementSupplier.trading_name.ilike(value),
            )
        )
    return query.order_by(models.ProcurementSupplier.legal_name.asc()).limit(min(max(limit, 1), 500)).all()


def create_supplier(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.SupplierCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementSupplier:
    duplicate = (
        db.query(models.ProcurementSupplier.id)
        .filter(
            models.ProcurementSupplier.amo_id == amo_id,
            func.upper(models.ProcurementSupplier.supplier_code) == payload.supplier_code.strip().upper(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Supplier code already exists.")

    vendor = None
    if payload.vendor_id is not None:
        vendor = (
            db.query(finance_models.Vendor)
            .filter(finance_models.Vendor.id == payload.vendor_id, finance_models.Vendor.amo_id == amo_id)
            .first()
        )
        if not vendor:
            raise HTTPException(status_code=400, detail="Finance vendor does not belong to this tenant.")
    else:
        vendor = (
            db.query(finance_models.Vendor)
            .filter(
                finance_models.Vendor.amo_id == amo_id,
                func.upper(finance_models.Vendor.code) == payload.supplier_code.strip().upper(),
            )
            .first()
        )
        if not vendor:
            vendor = finance_models.Vendor(
                amo_id=amo_id,
                code=payload.supplier_code.strip().upper(),
                name=payload.legal_name.strip(),
                email=payload.email,
                phone=payload.phone,
                remit_to_address=payload.physical_address,
                currency=payload.default_currency.upper(),
                is_active=True,
            )
            db.add(vendor)
            db.flush()

    supplier = models.ProcurementSupplier(
        amo_id=amo_id,
        supplier_code=payload.supplier_code.strip().upper(),
        legal_name=payload.legal_name.strip(),
        trading_name=payload.trading_name,
        supplier_type=payload.supplier_type.strip().upper(),
        vendor_id=vendor.id if vendor else None,
        qms_supplier_id=payload.qms_supplier_id,
        risk_level=payload.risk_level,
        email=payload.email,
        phone=payload.phone,
        website=payload.website,
        country=payload.country,
        physical_address=payload.physical_address,
        payment_terms=payload.payment_terms,
        default_currency=payload.default_currency.upper(),
        quality_contact_name=payload.quality_contact_name,
        quality_contact_email=payload.quality_contact_email,
        notes=payload.notes,
        created_by_user_id=actor_user_id,
        status=models.SupplierLifecycleStatus.UNDER_REVIEW,
    )
    db.add(supplier)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementSupplier",
        entity_id=str(supplier.id),
        action="create",
        actor_user_id=actor_user_id,
        detail={"supplier_code": supplier.supplier_code, "status": supplier.status.value},
    )
    return supplier


def update_supplier(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    payload: schemas.SupplierUpdate,
    actor_user_id: Optional[str],
) -> models.ProcurementSupplier:
    supplier = _get_supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    changes = payload.model_dump(exclude_unset=True)
    if "vendor_id" in changes and changes["vendor_id"] is not None:
        vendor = (
            db.query(finance_models.Vendor)
            .filter(finance_models.Vendor.id == changes["vendor_id"], finance_models.Vendor.amo_id == amo_id)
            .first()
        )
        if not vendor:
            raise HTTPException(status_code=400, detail="Finance vendor does not belong to this tenant.")
    for field, value in changes.items():
        if field == "default_currency" and value:
            value = value.upper()
        if field == "supplier_type" and value:
            value = value.upper()
        setattr(supplier, field, value)
    if supplier.vendor_id:
        vendor = (
            db.query(finance_models.Vendor)
            .filter(finance_models.Vendor.id == supplier.vendor_id, finance_models.Vendor.amo_id == amo_id)
            .first()
        )
        if vendor:
            vendor.name = supplier.legal_name
            vendor.email = supplier.email
            vendor.phone = supplier.phone
            vendor.remit_to_address = supplier.physical_address
            vendor.currency = supplier.default_currency
            db.add(vendor)
    db.add(supplier)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementSupplier",
        entity_id=str(supplier.id),
        action="update",
        actor_user_id=actor_user_id,
        detail={"fields": sorted(changes)},
    )
    return supplier


def add_supplier_scope(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    payload: schemas.ApprovalScopeCreate,
    actor_user_id: Optional[str],
) -> models.SupplierApprovalScope:
    supplier = _get_supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    scope = models.SupplierApprovalScope(
        amo_id=amo_id,
        supplier_id=supplier.id,
        site_code=payload.site_code.strip().upper(),
        category=payload.category.strip().upper(),
        product_family=payload.product_family.strip().upper(),
        manufacturer=payload.manufacturer,
        authority=payload.authority.strip().upper(),
        approval_number=payload.approval_number,
        effective_on=payload.effective_on,
        expires_on=payload.expires_on,
        restrictions=payload.restrictions,
        incoming_inspection_level=payload.incoming_inspection_level.strip().upper(),
        evidence_reference=payload.evidence_reference,
        qms_evaluation_id=payload.qms_evaluation_id,
        qms_audit_id=payload.qms_audit_id,
        status=models.ApprovalScopeStatus.ACTIVE,
        approved_by_user_id=actor_user_id,
        approved_at=datetime.utcnow(),
    )
    db.add(scope)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="SupplierApprovalScope",
        entity_id=str(scope.id),
        action="approve",
        actor_user_id=actor_user_id,
        detail={
            "supplier_id": supplier.id,
            "category": scope.category,
            "expires_on": scope.expires_on.isoformat() if scope.expires_on else None,
        },
    )
    return scope


def decide_supplier(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    payload: schemas.SupplierDecision,
    actor_user_id: Optional[str],
) -> models.ProcurementSupplier:
    supplier = _get_supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    mapping = {
        "APPROVE": models.SupplierLifecycleStatus.APPROVED,
        "CONDITIONALLY_APPROVE": models.SupplierLifecycleStatus.CONDITIONALLY_APPROVED,
        "RESTRICT": models.SupplierLifecycleStatus.RESTRICTED,
        "SUSPEND": models.SupplierLifecycleStatus.SUSPENDED,
        "REACTIVATE": models.SupplierLifecycleStatus.UNDER_REVIEW,
        "REJECT": models.SupplierLifecycleStatus.REJECTED,
        "ARCHIVE": models.SupplierLifecycleStatus.ARCHIVED,
    }
    new_status = mapping[payload.action]
    if new_status in {
        models.SupplierLifecycleStatus.APPROVED,
        models.SupplierLifecycleStatus.CONDITIONALLY_APPROVED,
    }:
        active_scope = (
            db.query(models.SupplierApprovalScope.id)
            .filter(
                models.SupplierApprovalScope.amo_id == amo_id,
                models.SupplierApprovalScope.supplier_id == supplier.id,
                models.SupplierApprovalScope.status == models.ApprovalScopeStatus.ACTIVE,
            )
            .first()
        )
        if not active_scope:
            raise HTTPException(status_code=409, detail="At least one active approval scope is required.")
        supplier.approved_at = datetime.utcnow()
        supplier.approved_by_user_id = actor_user_id
        supplier.suspension_reason = None
        supplier.suspended_at = None
        supplier.suspended_by_user_id = None
    if new_status in {
        models.SupplierLifecycleStatus.SUSPENDED,
        models.SupplierLifecycleStatus.RESTRICTED,
        models.SupplierLifecycleStatus.REJECTED,
    }:
        if not payload.reason:
            raise HTTPException(status_code=400, detail="A reason is required for this supplier decision.")
        supplier.suspension_reason = payload.reason
        supplier.suspended_at = datetime.utcnow()
        supplier.suspended_by_user_id = actor_user_id
    supplier.status = new_status
    supplier.is_active = new_status not in {
        models.SupplierLifecycleStatus.ARCHIVED,
        models.SupplierLifecycleStatus.REJECTED,
    }
    db.add(supplier)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementSupplier",
        entity_id=str(supplier.id),
        action=payload.action.lower(),
        actor_user_id=actor_user_id,
        detail={"status": new_status.value, "reason": payload.reason},
    )
    return supplier


def list_requisitions(
    db: Session,
    *,
    amo_id: str,
    status_filter: Optional[models.RequisitionStatus] = None,
    limit: int = 100,
) -> list[models.ProcurementRequisition]:
    query = db.query(models.ProcurementRequisition).filter(models.ProcurementRequisition.amo_id == amo_id)
    if status_filter:
        query = query.filter(models.ProcurementRequisition.status == status_filter)
    return query.order_by(models.ProcurementRequisition.created_at.desc()).limit(min(max(limit, 1), 500)).all()


def create_requisition(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.RequisitionCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementRequisition:
    existing = (
        db.query(models.ProcurementRequisition.id)
        .filter(
            models.ProcurementRequisition.amo_id == amo_id,
            models.ProcurementRequisition.requisition_number == payload.requisition_number.strip().upper(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Requisition number already exists.")
    requisition = models.ProcurementRequisition(
        amo_id=amo_id,
        requisition_number=payload.requisition_number.strip().upper(),
        title=payload.title.strip(),
        requesting_department=payload.requesting_department.strip().upper(),
        priority=payload.priority,
        required_by=payload.required_by,
        cost_centre=payload.cost_centre,
        project_code=payload.project_code,
        budget_reference=payload.budget_reference,
        justification=payload.justification,
        source_module=payload.source_module,
        source_record_id=payload.source_record_id,
        work_order_id=payload.work_order_id,
        task_card_id=payload.task_card_id,
        aircraft_serial_number=payload.aircraft_serial_number,
        requested_by_user_id=actor_user_id,
        status=models.RequisitionStatus.DRAFT,
    )
    db.add(requisition)
    db.flush()
    for index, line in enumerate(payload.lines, start=1):
        db.add(
            models.ProcurementRequisitionLine(
                requisition_id=requisition.id,
                line_number=index,
                **line.model_dump(),
            )
        )
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementRequisition",
        entity_id=str(requisition.id),
        action="create",
        actor_user_id=actor_user_id,
        detail={
            "requisition_number": requisition.requisition_number,
            "source_module": requisition.source_module,
            "line_count": len(payload.lines),
        },
    )
    return requisition


def transition_requisition(
    db: Session,
    *,
    amo_id: str,
    requisition_id: int,
    payload: schemas.RequisitionTransition,
    actor_user_id: Optional[str],
) -> models.ProcurementRequisition:
    requisition = (
        db.query(models.ProcurementRequisition)
        .filter(
            models.ProcurementRequisition.amo_id == amo_id,
            models.ProcurementRequisition.id == requisition_id,
        )
        .first()
    )
    if not requisition:
        raise HTTPException(status_code=404, detail="Requisition was not found.")

    action = payload.action
    if action in {"TECHNICAL_APPROVE", "BUDGET_APPROVE", "APPROVE"} and actor_user_id == requisition.requested_by_user_id:
        raise HTTPException(status_code=409, detail="A requester cannot approve their own requisition.")

    if action == "SUBMIT":
        if requisition.status != models.RequisitionStatus.DRAFT:
            raise HTTPException(status_code=409, detail="Only draft requisitions can be submitted.")
        requisition.status = models.RequisitionStatus.SUBMITTED
        requisition.submitted_at = datetime.utcnow()
    elif action == "TECHNICAL_APPROVE":
        if requisition.status not in {models.RequisitionStatus.SUBMITTED, models.RequisitionStatus.TECHNICAL_REVIEW}:
            raise HTTPException(status_code=409, detail="Requisition is not awaiting technical review.")
        requisition.technical_reviewed_by_user_id = actor_user_id
        requisition.status = models.RequisitionStatus.BUDGET_REVIEW
    elif action == "BUDGET_APPROVE":
        if requisition.status != models.RequisitionStatus.BUDGET_REVIEW or not requisition.technical_reviewed_by_user_id:
            raise HTTPException(status_code=409, detail="Technical approval is required before budget approval.")
        requisition.budget_reviewed_by_user_id = actor_user_id
        requisition.status = models.RequisitionStatus.SOURCING
    elif action == "APPROVE":
        if requisition.status != models.RequisitionStatus.SOURCING:
            raise HTTPException(status_code=409, detail="Requisition must complete sourcing before approval.")
        if not requisition.technical_reviewed_by_user_id or not requisition.budget_reviewed_by_user_id:
            raise HTTPException(status_code=409, detail="Technical and budget reviews are required.")
        requisition.status = models.RequisitionStatus.APPROVED
        requisition.approved_at = datetime.utcnow()
    elif action == "REJECT":
        if not payload.reason:
            raise HTTPException(status_code=400, detail="A rejection reason is required.")
        requisition.status = models.RequisitionStatus.REJECTED
    elif action == "CANCEL":
        requisition.status = models.RequisitionStatus.CANCELLED
    elif action == "CLOSE":
        requisition.status = models.RequisitionStatus.CLOSED
    else:
        raise HTTPException(status_code=400, detail="Unsupported requisition transition.")

    db.add(requisition)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementRequisition",
        entity_id=str(requisition.id),
        action=action.lower(),
        actor_user_id=actor_user_id,
        detail={"status": requisition.status.value, "reason": payload.reason},
    )
    return requisition


def create_rfq(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.RFQCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementRFQ:
    requisition = (
        db.query(models.ProcurementRequisition)
        .filter(
            models.ProcurementRequisition.amo_id == amo_id,
            models.ProcurementRequisition.id == payload.requisition_id,
        )
        .first()
    )
    if not requisition:
        raise HTTPException(status_code=404, detail="Requisition was not found.")
    if requisition.status not in {
        models.RequisitionStatus.SOURCING,
        models.RequisitionStatus.APPROVED,
    }:
        raise HTTPException(status_code=409, detail="Requisition is not ready for sourcing.")

    suppliers = (
        db.query(models.ProcurementSupplier)
        .filter(
            models.ProcurementSupplier.amo_id == amo_id,
            models.ProcurementSupplier.id.in_(set(payload.supplier_ids)),
            models.ProcurementSupplier.is_active.is_(True),
        )
        .all()
    )
    if len(suppliers) != len(set(payload.supplier_ids)):
        raise HTTPException(status_code=400, detail="One or more suppliers are invalid or inactive.")

    rfq = models.ProcurementRFQ(
        amo_id=amo_id,
        rfq_number=payload.rfq_number.strip().upper(),
        requisition_id=requisition.id,
        title=payload.title,
        response_due_at=payload.response_due_at,
        terms=payload.terms,
        quality_clauses=payload.quality_clauses,
        status=models.RFQStatus.ISSUED if payload.issue_immediately else models.RFQStatus.DRAFT,
        issued_at=datetime.utcnow() if payload.issue_immediately else None,
        created_by_user_id=actor_user_id,
    )
    db.add(rfq)
    db.flush()
    for supplier_id in sorted(set(payload.supplier_ids)):
        db.add(models.ProcurementRFQSupplier(rfq_id=rfq.id, supplier_id=supplier_id))
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementRFQ",
        entity_id=str(rfq.id),
        action="issue" if payload.issue_immediately else "create",
        actor_user_id=actor_user_id,
        detail={"rfq_number": rfq.rfq_number, "supplier_count": len(set(payload.supplier_ids))},
    )
    return rfq


def list_rfqs(db: Session, *, amo_id: str, limit: int = 100) -> list[models.ProcurementRFQ]:
    return (
        db.query(models.ProcurementRFQ)
        .filter(models.ProcurementRFQ.amo_id == amo_id)
        .order_by(models.ProcurementRFQ.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


def create_quote(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.QuoteCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementQuote:
    rfq = (
        db.query(models.ProcurementRFQ)
        .filter(models.ProcurementRFQ.amo_id == amo_id, models.ProcurementRFQ.id == payload.rfq_id)
        .first()
    )
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ was not found.")
    invited = (
        db.query(models.ProcurementRFQSupplier)
        .filter(
            models.ProcurementRFQSupplier.rfq_id == rfq.id,
            models.ProcurementRFQSupplier.supplier_id == payload.supplier_id,
        )
        .first()
    )
    if not invited:
        raise HTTPException(status_code=409, detail="Supplier was not invited to this RFQ.")

    line_total = sum((Decimal(str(line.quantity)) * line.unit_price for line in payload.lines), Decimal("0"))
    total = line_total + payload.freight_amount + payload.tax_amount
    quote = models.ProcurementQuote(
        amo_id=amo_id,
        rfq_id=rfq.id,
        supplier_id=payload.supplier_id,
        quote_reference=payload.quote_reference.strip(),
        currency=payload.currency.upper(),
        freight_amount=payload.freight_amount,
        tax_amount=payload.tax_amount,
        total_amount=total,
        lead_time_days=payload.lead_time_days,
        valid_until=payload.valid_until,
        certification_offered=payload.certification_offered,
        warranty_terms=payload.warranty_terms,
        technical_deviations=payload.technical_deviations,
        status=models.QuoteStatus.RECEIVED,
    )
    db.add(quote)
    db.flush()
    for line in payload.lines:
        db.add(models.ProcurementQuoteLine(quote_id=quote.id, **line.model_dump()))
    invited.responded_at = datetime.utcnow()
    rfq.status = models.RFQStatus.PARTIALLY_RESPONDED
    db.add_all([invited, rfq])
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementQuote",
        entity_id=str(quote.id),
        action="receive",
        actor_user_id=actor_user_id,
        detail={"quote_reference": quote.quote_reference, "total_amount": str(total)},
    )
    return quote


def evaluate_quote(
    db: Session,
    *,
    amo_id: str,
    quote_id: int,
    payload: schemas.QuoteEvaluate,
    actor_user_id: Optional[str],
) -> models.ProcurementQuote:
    quote = (
        db.query(models.ProcurementQuote)
        .filter(models.ProcurementQuote.amo_id == amo_id, models.ProcurementQuote.id == quote_id)
        .first()
    )
    if not quote:
        raise HTTPException(status_code=404, detail="Quote was not found.")
    quote.status = payload.status
    quote.evaluation_score = payload.evaluation_score
    quote.evaluation_notes = payload.evaluation_notes
    quote.evaluated_by_user_id = actor_user_id
    quote.evaluated_at = datetime.utcnow()
    db.add(quote)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementQuote",
        entity_id=str(quote.id),
        action="evaluate",
        actor_user_id=actor_user_id,
        detail={"status": quote.status.value, "score": quote.evaluation_score},
    )
    return quote


def list_quotes(db: Session, *, amo_id: str, limit: int = 100) -> list[models.ProcurementQuote]:
    return (
        db.query(models.ProcurementQuote)
        .filter(models.ProcurementQuote.amo_id == amo_id)
        .order_by(models.ProcurementQuote.received_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


def create_purchase_order(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.PurchaseOrderCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementPurchaseOrder:
    supplier = _get_supplier(db, amo_id=amo_id, supplier_id=payload.supplier_id)
    duplicate = (
        db.query(models.ProcurementPurchaseOrder.id)
        .filter(
            models.ProcurementPurchaseOrder.amo_id == amo_id,
            models.ProcurementPurchaseOrder.po_number == payload.po_number.strip().upper(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Purchase-order number already exists.")

    subtotal = sum((Decimal(str(line.quantity)) * line.unit_price for line in payload.lines), Decimal("0"))
    total = subtotal + payload.freight_amount + payload.tax_amount
    po = models.ProcurementPurchaseOrder(
        amo_id=amo_id,
        po_number=payload.po_number.strip().upper(),
        supplier_id=supplier.id,
        quote_id=payload.quote_id,
        requisition_id=payload.requisition_id,
        priority=payload.priority,
        currency=payload.currency.upper(),
        subtotal=subtotal,
        freight_amount=payload.freight_amount,
        tax_amount=payload.tax_amount,
        total_amount=total,
        delivery_terms=payload.delivery_terms,
        payment_terms=payload.payment_terms or supplier.payment_terms,
        quality_clauses=payload.quality_clauses,
        ship_to_location_id=payload.ship_to_location_id,
        promised_delivery_date=payload.promised_delivery_date,
        override_reference=payload.override_reference,
        override_reason=payload.override_reason,
        requested_by_user_id=actor_user_id,
        created_by_user_id=actor_user_id,
        status=models.PurchaseOrderStatus.PENDING_TECHNICAL_REVIEW,
    )
    db.add(po)
    db.flush()
    for index, line in enumerate(payload.lines, start=1):
        db.add(
            models.ProcurementPurchaseOrderLine(
                purchase_order_id=po.id,
                line_number=index,
                **line.model_dump(),
            )
        )
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementPurchaseOrder",
        entity_id=str(po.id),
        action="create",
        actor_user_id=actor_user_id,
        detail={"po_number": po.po_number, "supplier_id": po.supplier_id, "total_amount": str(total)},
    )
    return po


def _get_po(db: Session, *, amo_id: str, po_id: int) -> models.ProcurementPurchaseOrder:
    po = (
        db.query(models.ProcurementPurchaseOrder)
        .filter(
            models.ProcurementPurchaseOrder.amo_id == amo_id,
            models.ProcurementPurchaseOrder.id == po_id,
        )
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order was not found.")
    return po


def approve_purchase_order(
    db: Session,
    *,
    amo_id: str,
    po_id: int,
    payload: schemas.PurchaseOrderApproval,
    actor_user_id: Optional[str],
    actor_is_quality: bool,
) -> models.ProcurementPurchaseOrder:
    po = _get_po(db, amo_id=amo_id, po_id=po_id)
    if actor_user_id in {po.requested_by_user_id, po.created_by_user_id}:
        raise HTTPException(status_code=409, detail="The requester/creator cannot approve this purchase order.")

    stage = payload.stage
    if stage == "TECHNICAL":
        if po.status != models.PurchaseOrderStatus.PENDING_TECHNICAL_REVIEW:
            raise HTTPException(status_code=409, detail="Purchase order is not awaiting technical review.")
        po.technical_approved_by_user_id = actor_user_id
        po.status = models.PurchaseOrderStatus.PENDING_BUDGET_APPROVAL
    elif stage == "BUDGET":
        if po.status != models.PurchaseOrderStatus.PENDING_BUDGET_APPROVAL or not po.technical_approved_by_user_id:
            raise HTTPException(status_code=409, detail="Technical approval is required first.")
        po.budget_approved_by_user_id = actor_user_id
        po.status = models.PurchaseOrderStatus.PENDING_PROCUREMENT_APPROVAL
    elif stage == "PROCUREMENT":
        if po.status != models.PurchaseOrderStatus.PENDING_PROCUREMENT_APPROVAL or not po.budget_approved_by_user_id:
            raise HTTPException(status_code=409, detail="Budget approval is required first.")
        po.procurement_approved_by_user_id = actor_user_id
        po.status = models.PurchaseOrderStatus.PENDING_QUALITY_APPROVAL
    elif stage in {"QUALITY", "FINAL"}:
        if po.status != models.PurchaseOrderStatus.PENDING_QUALITY_APPROVAL:
            raise HTTPException(status_code=409, detail="Purchase order is not awaiting Quality approval.")
        if not actor_is_quality:
            raise HTTPException(status_code=403, detail="Final release requires Quality authorization.")
        if not po.procurement_approved_by_user_id:
            raise HTTPException(status_code=409, detail="Procurement approval is required first.")
        categories = {"PART" if line.part_number else "SERVICE" for line in po.lines}
        allow_override = bool(po.override_reference and po.override_reason)
        assert_supplier_eligible(
            db,
            amo_id=amo_id,
            supplier_id=po.supplier_id,
            categories=categories,
            allow_controlled_override=allow_override,
            override_reference=po.override_reference,
            override_reason=po.override_reason,
        )
        po.quality_approved_by_user_id = actor_user_id
        po.approved_at = datetime.utcnow()
        po.status = models.PurchaseOrderStatus.APPROVED
    else:
        raise HTTPException(status_code=400, detail="Unsupported approval stage.")

    db.add(po)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementPurchaseOrder",
        entity_id=str(po.id),
        action=f"approve_{stage.lower()}",
        actor_user_id=actor_user_id,
        detail={"status": po.status.value, "comment": payload.comment},
    )
    return po


def send_purchase_order(
    db: Session,
    *,
    amo_id: str,
    po_id: int,
    actor_user_id: Optional[str],
) -> models.ProcurementPurchaseOrder:
    po = _get_po(db, amo_id=amo_id, po_id=po_id)
    if po.status != models.PurchaseOrderStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Only approved purchase orders can be sent.")
    po.status = models.PurchaseOrderStatus.SENT
    po.sent_at = datetime.utcnow()
    db.add(po)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementPurchaseOrder",
        entity_id=str(po.id),
        action="send",
        actor_user_id=actor_user_id,
        detail={"sent_at": po.sent_at.isoformat()},
    )
    return po


def acknowledge_purchase_order(
    db: Session,
    *,
    amo_id: str,
    po_id: int,
    payload: schemas.PurchaseOrderAcknowledge,
    actor_user_id: Optional[str],
) -> models.ProcurementPurchaseOrder:
    po = _get_po(db, amo_id=amo_id, po_id=po_id)
    if po.status not in {models.PurchaseOrderStatus.SENT, models.PurchaseOrderStatus.APPROVED}:
        raise HTTPException(status_code=409, detail="Purchase order is not awaiting acknowledgement.")
    po.supplier_ack_reference = payload.supplier_ack_reference
    po.promised_delivery_date = payload.promised_delivery_date or po.promised_delivery_date
    po.acknowledged_at = datetime.utcnow()
    po.status = models.PurchaseOrderStatus.ACKNOWLEDGED
    db.add(po)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementPurchaseOrder",
        entity_id=str(po.id),
        action="acknowledge",
        actor_user_id=actor_user_id,
        detail={"supplier_ack_reference": po.supplier_ack_reference},
    )
    return po


def list_purchase_orders(
    db: Session,
    *,
    amo_id: str,
    status_filter: Optional[models.PurchaseOrderStatus] = None,
    limit: int = 100,
) -> list[models.ProcurementPurchaseOrder]:
    query = db.query(models.ProcurementPurchaseOrder).filter(models.ProcurementPurchaseOrder.amo_id == amo_id)
    if status_filter:
        query = query.filter(models.ProcurementPurchaseOrder.status == status_filter)
    return query.order_by(models.ProcurementPurchaseOrder.created_at.desc()).limit(min(max(limit, 1), 500)).all()


def create_receipt(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.ReceiptCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementReceipt:
    duplicate = (
        db.query(models.ProcurementReceipt.id)
        .filter(
            models.ProcurementReceipt.amo_id == amo_id,
            models.ProcurementReceipt.receipt_number == payload.receipt_number.strip().upper(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Receipt number already exists.")
    po = _get_po(db, amo_id=amo_id, po_id=payload.purchase_order_id)
    if po.status not in {
        models.PurchaseOrderStatus.APPROVED,
        models.PurchaseOrderStatus.SENT,
        models.PurchaseOrderStatus.ACKNOWLEDGED,
        models.PurchaseOrderStatus.PARTIALLY_SHIPPED,
        models.PurchaseOrderStatus.SHIPPED,
        models.PurchaseOrderStatus.PARTIALLY_RECEIVED,
    }:
        raise HTTPException(status_code=409, detail="Purchase order is not open for receipt.")

    assert_supplier_eligible(
        db,
        amo_id=amo_id,
        supplier_id=po.supplier_id,
        categories={"PART" if line.part_number else "SERVICE" for line in po.lines},
        allow_controlled_override=bool(po.override_reference and po.override_reason),
        override_reference=po.override_reference,
        override_reason=po.override_reason,
    )

    po_line_map = {line.id: line for line in po.lines}
    for line in payload.lines:
        po_line = po_line_map.get(line.purchase_order_line_id)
        if not po_line:
            raise HTTPException(status_code=400, detail="Receipt line does not belong to this purchase order.")
        remaining = float(po_line.quantity) - float(po_line.received_quantity or 0)
        if line.quantity > remaining:
            raise HTTPException(status_code=409, detail=f"Receipt quantity exceeds remaining quantity for PO line {po_line.line_number}.")
        if line.part_number.strip().upper() != (po_line.part_number or "").strip().upper():
            raise HTTPException(status_code=409, detail=f"Part number does not match PO line {po_line.line_number}.")

    receipt = models.ProcurementReceipt(
        amo_id=amo_id,
        receipt_number=payload.receipt_number.strip().upper(),
        purchase_order_id=po.id,
        status=models.ReceiptStatus.QUARANTINED,
        delivery_note_number=payload.delivery_note_number,
        airway_bill_number=payload.airway_bill_number,
        supplier_shipment_reference=payload.supplier_shipment_reference,
        package_condition=payload.package_condition,
        received_by_user_id=actor_user_id,
        quarantine_location_id=payload.quarantine_location_id,
        notes=payload.notes,
    )
    db.add(receipt)
    db.flush()
    for line in payload.lines:
        db.add(
            models.ProcurementReceiptLine(
                receipt_id=receipt.id,
                **line.model_dump(),
            )
        )
    po.status = models.PurchaseOrderStatus.RECEIVED_PENDING_INSPECTION
    db.add(po)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementReceipt",
        entity_id=str(receipt.id),
        action="receive_to_quarantine",
        actor_user_id=actor_user_id,
        detail={"receipt_number": receipt.receipt_number, "po_id": po.id, "status": receipt.status.value},
    )
    return receipt


def list_receipts(
    db: Session,
    *,
    amo_id: str,
    status_filter: Optional[models.ReceiptStatus] = None,
    limit: int = 100,
) -> list[models.ProcurementReceipt]:
    query = db.query(models.ProcurementReceipt).filter(models.ProcurementReceipt.amo_id == amo_id)
    if status_filter:
        query = query.filter(models.ProcurementReceipt.status == status_filter)
    return query.order_by(models.ProcurementReceipt.received_at.desc()).limit(min(max(limit, 1), 500)).all()


def inspect_receipt(
    db: Session,
    *,
    amo_id: str,
    receipt_id: int,
    payload: schemas.InspectionCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementReceipt:
    receipt = (
        db.query(models.ProcurementReceipt)
        .filter(models.ProcurementReceipt.amo_id == amo_id, models.ProcurementReceipt.id == receipt_id)
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt was not found.")
    if actor_user_id == receipt.received_by_user_id:
        raise HTTPException(status_code=409, detail="The receiver cannot perform the independent receiving inspection.")
    if receipt.status not in {
        models.ReceiptStatus.QUARANTINED,
        models.ReceiptStatus.DOCUMENT_REVIEW,
        models.ReceiptStatus.PHYSICAL_INSPECTION,
    }:
        raise HTTPException(status_code=409, detail="Receipt is not awaiting inspection.")

    inspection = models.ProcurementReceivingInspection(
        amo_id=amo_id,
        receipt_id=receipt.id,
        documentation_complete=payload.documentation_complete,
        physical_condition_acceptable=payload.physical_condition_acceptable,
        supplier_scope_valid=payload.supplier_scope_valid,
        part_identity_matches=payload.part_identity_matches,
        traceability_acceptable=payload.traceability_acceptable,
        shelf_life_acceptable=payload.shelf_life_acceptable,
        suspected_unapproved_part=payload.suspected_unapproved_part,
        disposition=payload.disposition,
        findings=payload.findings,
        conditions=payload.conditions,
        inspected_by_user_id=actor_user_id,
    )
    db.add(inspection)
    for line in receipt.lines:
        line.disposition = payload.line_dispositions.get(line.id, payload.disposition)
        if line.disposition not in {
            models.InspectionDisposition.ACCEPTED,
            models.InspectionDisposition.CONDITIONALLY_ACCEPTED,
        }:
            line.discrepancy_notes = payload.findings
        db.add(line)

    acceptable = all(
        [
            payload.documentation_complete,
            payload.physical_condition_acceptable,
            payload.supplier_scope_valid,
            payload.part_identity_matches,
            payload.traceability_acceptable,
            payload.shelf_life_acceptable,
            not payload.suspected_unapproved_part,
            payload.disposition in {
                models.InspectionDisposition.ACCEPTED,
                models.InspectionDisposition.CONDITIONALLY_ACCEPTED,
            },
        ]
    )
    if acceptable:
        receipt.status = models.ReceiptStatus.ACCEPTED_PENDING_RELEASE
    elif payload.disposition == models.InspectionDisposition.RETURN_TO_SUPPLIER:
        receipt.status = models.ReceiptStatus.RETURN_PENDING
    elif payload.disposition == models.InspectionDisposition.REJECTED:
        receipt.status = models.ReceiptStatus.REJECTED
    else:
        receipt.status = models.ReceiptStatus.QUARANTINED

    receipt.inspection_started_at = receipt.inspection_started_at or datetime.utcnow()
    receipt.inspection_completed_at = datetime.utcnow()
    db.add(receipt)

    if payload.suspected_unapproved_part or payload.disposition == models.InspectionDisposition.ESCALATED_TO_QUALITY:
        hold = models.ProcurementQualityHold(
            amo_id=amo_id,
            hold_number=f"AUTO-RCV-{receipt.id}-{int(datetime.utcnow().timestamp())}",
            target_type="RECEIPT",
            target_id=str(receipt.id),
            reason=payload.findings or "Receiving inspection escalated to Quality.",
            placed_by_user_id=actor_user_id,
        )
        db.add(hold)

    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementReceipt",
        entity_id=str(receipt.id),
        action="inspect",
        actor_user_id=actor_user_id,
        detail={"disposition": payload.disposition.value, "status": receipt.status.value},
    )
    return receipt


def release_receipt(
    db: Session,
    *,
    amo_id: str,
    receipt_id: int,
    payload: schemas.ReceiptRelease,
    actor_user_id: Optional[str],
) -> models.ProcurementReceipt:
    receipt = (
        db.query(models.ProcurementReceipt)
        .filter(models.ProcurementReceipt.amo_id == amo_id, models.ProcurementReceipt.id == receipt_id)
        .first()
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt was not found.")
    if actor_user_id == receipt.received_by_user_id:
        raise HTTPException(status_code=409, detail="The receiver cannot release the same receipt.")
    if receipt.status != models.ReceiptStatus.ACCEPTED_PENDING_RELEASE:
        raise HTTPException(status_code=409, detail="Receipt has not passed receiving inspection.")

    po = receipt.purchase_order
    holds = _active_holds(
        db,
        amo_id=amo_id,
        targets=[
            ("RECEIPT", str(receipt.id)),
            ("PURCHASE_ORDER", str(po.id)),
            ("SUPPLIER", str(po.supplier_id)),
        ],
    )
    if holds:
        raise HTTPException(status_code=409, detail="Quality hold prevents receipt release.")

    for line in receipt.lines:
        if line.disposition not in {
            models.InspectionDisposition.ACCEPTED,
            models.InspectionDisposition.CONDITIONALLY_ACCEPTED,
        }:
            continue

        part = None
        if line.inventory_part_id:
            part = (
                db.query(inventory_models.InventoryPart)
                .filter(
                    inventory_models.InventoryPart.amo_id == amo_id,
                    inventory_models.InventoryPart.id == line.inventory_part_id,
                )
                .first()
            )
        if not part:
            part = (
                db.query(inventory_models.InventoryPart)
                .filter(
                    inventory_models.InventoryPart.amo_id == amo_id,
                    func.upper(inventory_models.InventoryPart.part_number) == line.part_number.strip().upper(),
                )
                .first()
            )
        if not part:
            raise HTTPException(
                status_code=409,
                detail=f"Part master {line.part_number} must exist before Quality release.",
            )

        movement = inventory_services.receive_inventory(
            db,
            amo_id=amo_id,
            payload=inventory_schemas.InventoryReceiveRequest(
                part_number=part.part_number,
                part_description=part.description,
                quantity=line.quantity,
                uom=line.uom,
                lot_number=line.lot_number,
                serial_number=line.serial_number,
                to_location_id=line.target_location_id,
                condition=inventory_models.InventoryConditionEnum.SERVICEABLE,
                is_serialized=part.is_serialized,
                is_lot_controlled=part.is_lot_controlled,
                received_date=receipt.received_at.date(),
                reference_type="PROCUREMENT_RECEIPT",
                reference_id=str(receipt.id),
                idempotency_key=f"procurement-release:{amo_id}:{receipt.id}:{line.id}",
                notes=payload.release_comment,
            ),
            actor_user_id=actor_user_id,
        )
        line.released_inventory_movement_id = movement.id
        po_line = (
            db.query(models.ProcurementPurchaseOrderLine)
            .filter(models.ProcurementPurchaseOrderLine.id == line.purchase_order_line_id)
            .first()
        )
        if po_line:
            po_line.received_quantity = float(po_line.received_quantity or 0) + float(line.quantity)
            db.add(po_line)
        db.add(line)

    receipt.status = models.ReceiptStatus.RELEASED
    receipt.released_at = datetime.utcnow()
    receipt.released_by_user_id = actor_user_id
    db.add(receipt)

    all_received = all(float(line.received_quantity or 0) >= float(line.quantity) for line in po.lines)
    po.status = models.PurchaseOrderStatus.FULFILLED if all_received else models.PurchaseOrderStatus.PARTIALLY_RECEIVED
    db.add(po)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementReceipt",
        entity_id=str(receipt.id),
        action="quality_release",
        actor_user_id=actor_user_id,
        detail={"status": receipt.status.value, "po_status": po.status.value},
    )
    return receipt


def create_quality_hold(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.QualityHoldCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementQualityHold:
    hold = models.ProcurementQualityHold(
        amo_id=amo_id,
        hold_number=payload.hold_number.strip().upper(),
        target_type=payload.target_type.strip().upper(),
        target_id=payload.target_id,
        reason=payload.reason,
        qms_finding_id=payload.qms_finding_id,
        qms_car_id=payload.qms_car_id,
        placed_by_user_id=actor_user_id,
    )
    db.add(hold)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementQualityHold",
        entity_id=str(hold.id),
        action="place",
        actor_user_id=actor_user_id,
        detail={"target_type": hold.target_type, "target_id": hold.target_id},
    )
    return hold


def release_quality_hold(
    db: Session,
    *,
    amo_id: str,
    hold_id: int,
    payload: schemas.QualityHoldRelease,
    actor_user_id: Optional[str],
) -> models.ProcurementQualityHold:
    hold = (
        db.query(models.ProcurementQualityHold)
        .filter(
            models.ProcurementQualityHold.amo_id == amo_id,
            models.ProcurementQualityHold.id == hold_id,
        )
        .first()
    )
    if not hold:
        raise HTTPException(status_code=404, detail="Quality hold was not found.")
    if hold.status != models.QualityHoldStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Quality hold is not active.")
    hold.status = models.QualityHoldStatus.RELEASED
    hold.released_by_user_id = actor_user_id
    hold.released_at = datetime.utcnow()
    hold.release_reason = payload.release_reason
    db.add(hold)
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementQualityHold",
        entity_id=str(hold.id),
        action="release",
        actor_user_id=actor_user_id,
        detail={"release_reason": payload.release_reason},
    )
    return hold


def list_quality_holds(
    db: Session,
    *,
    amo_id: str,
    active_only: bool = True,
    limit: int = 100,
) -> list[models.ProcurementQualityHold]:
    query = db.query(models.ProcurementQualityHold).filter(models.ProcurementQualityHold.amo_id == amo_id)
    if active_only:
        query = query.filter(models.ProcurementQualityHold.status == models.QualityHoldStatus.ACTIVE)
    return query.order_by(models.ProcurementQualityHold.placed_at.desc()).limit(min(max(limit, 1), 500)).all()


def create_invoice_match(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InvoiceMatchCreate,
    actor_user_id: Optional[str],
) -> models.ProcurementInvoiceMatch:
    po = _get_po(db, amo_id=amo_id, po_id=payload.purchase_order_id)
    released_total = Decimal("0")
    po_line_by_id = {line.id: line for line in po.lines}
    for receipt in po.receipts:
        if receipt.status != models.ReceiptStatus.RELEASED:
            continue
        for receipt_line in receipt.lines:
            po_line = po_line_by_id.get(receipt_line.purchase_order_line_id)
            if po_line:
                released_total += Decimal(str(receipt_line.quantity)) * Decimal(str(po_line.unit_price))
    variance = payload.invoice_total - released_total
    blocked = bool(
        _active_holds(
            db,
            amo_id=amo_id,
            targets=[("PURCHASE_ORDER", str(po.id)), ("SUPPLIER", str(po.supplier_id))],
        )
    )
    if blocked:
        match_status = models.InvoiceMatchStatus.BLOCKED
    elif abs(variance) <= payload.tolerance_amount:
        match_status = models.InvoiceMatchStatus.MATCHED
    else:
        match_status = models.InvoiceMatchStatus.VARIANCE

    match = models.ProcurementInvoiceMatch(
        amo_id=amo_id,
        purchase_order_id=po.id,
        invoice_reference=payload.invoice_reference,
        invoice_total=payload.invoice_total,
        received_total=released_total,
        variance_amount=variance,
        status=match_status,
        finance_reference=payload.finance_reference,
        notes=payload.notes,
        matched_by_user_id=actor_user_id,
    )
    db.add(match)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        entity_type="ProcurementInvoiceMatch",
        entity_id=str(match.id),
        action="three_way_match",
        actor_user_id=actor_user_id,
        detail={"status": match.status.value, "variance": str(variance)},
    )
    return match


def dashboard(db: Session, *, amo_id: str) -> schemas.DashboardResponse:
    today = date.today()
    counters = {
        "open_requisitions": db.query(func.count(models.ProcurementRequisition.id)).filter(
            models.ProcurementRequisition.amo_id == amo_id,
            models.ProcurementRequisition.status.notin_(
                [models.RequisitionStatus.CLOSED, models.RequisitionStatus.CANCELLED, models.RequisitionStatus.REJECTED]
            ),
        ).scalar() or 0,
        "rfqs_in_market": db.query(func.count(models.ProcurementRFQ.id)).filter(
            models.ProcurementRFQ.amo_id == amo_id,
            models.ProcurementRFQ.status.in_(
                [models.RFQStatus.ISSUED, models.RFQStatus.PARTIALLY_RESPONDED, models.RFQStatus.EVALUATION]
            ),
        ).scalar() or 0,
        "orders_pending_approval": db.query(func.count(models.ProcurementPurchaseOrder.id)).filter(
            models.ProcurementPurchaseOrder.amo_id == amo_id,
            models.ProcurementPurchaseOrder.status.in_(
                [
                    models.PurchaseOrderStatus.PENDING_TECHNICAL_REVIEW,
                    models.PurchaseOrderStatus.PENDING_BUDGET_APPROVAL,
                    models.PurchaseOrderStatus.PENDING_PROCUREMENT_APPROVAL,
                    models.PurchaseOrderStatus.PENDING_QUALITY_APPROVAL,
                ]
            ),
        ).scalar() or 0,
        "quarantine_receipts": db.query(func.count(models.ProcurementReceipt.id)).filter(
            models.ProcurementReceipt.amo_id == amo_id,
            models.ProcurementReceipt.status.in_(
                [
                    models.ReceiptStatus.QUARANTINED,
                    models.ReceiptStatus.DOCUMENT_REVIEW,
                    models.ReceiptStatus.PHYSICAL_INSPECTION,
                    models.ReceiptStatus.ACCEPTED_PENDING_RELEASE,
                ]
            ),
        ).scalar() or 0,
        "active_quality_holds": db.query(func.count(models.ProcurementQualityHold.id)).filter(
            models.ProcurementQualityHold.amo_id == amo_id,
            models.ProcurementQualityHold.status == models.QualityHoldStatus.ACTIVE,
        ).scalar() or 0,
        "supplier_approvals_expiring": db.query(func.count(models.SupplierApprovalScope.id)).filter(
            models.SupplierApprovalScope.amo_id == amo_id,
            models.SupplierApprovalScope.status == models.ApprovalScopeStatus.ACTIVE,
            models.SupplierApprovalScope.expires_on.isnot(None),
            models.SupplierApprovalScope.expires_on >= today,
            models.SupplierApprovalScope.expires_on <= date.fromordinal(today.toordinal() + 60),
        ).scalar() or 0,
    }

    pending_reqs = list_requisitions(db, amo_id=amo_id, limit=8)
    pending_pos = list_purchase_orders(db, amo_id=amo_id, limit=8)
    receipts = list_receipts(db, amo_id=amo_id, limit=8)
    suppliers = list_suppliers(db, amo_id=amo_id, limit=50)

    action_queue = [
        {
            "kind": "requisition",
            "id": row.id,
            "reference": row.requisition_number,
            "title": row.title,
            "status": row.status.value,
            "priority": row.priority.value,
            "due_date": row.required_by.isoformat() if row.required_by else None,
        }
        for row in pending_reqs
        if row.status not in {models.RequisitionStatus.CLOSED, models.RequisitionStatus.CANCELLED}
    ][:6]
    action_queue.extend(
        {
            "kind": "purchase_order",
            "id": row.id,
            "reference": row.po_number,
            "title": row.supplier.legal_name if row.supplier else "Supplier",
            "status": row.status.value,
            "priority": row.priority.value,
            "due_date": row.promised_delivery_date.isoformat() if row.promised_delivery_date else None,
        }
        for row in pending_pos
        if row.status.value.startswith("PENDING_")
    )

    supply_exceptions = [
        {
            "kind": "late_order",
            "id": row.id,
            "reference": row.po_number,
            "supplier": row.supplier.legal_name if row.supplier else None,
            "promised_delivery_date": row.promised_delivery_date.isoformat(),
        }
        for row in pending_pos
        if row.promised_delivery_date
        and row.promised_delivery_date < today
        and row.status not in {
            models.PurchaseOrderStatus.FULFILLED,
            models.PurchaseOrderStatus.CLOSED,
            models.PurchaseOrderStatus.CANCELLED,
        }
    ][:8]

    quality_control = [
        {
            "kind": "receipt",
            "id": row.id,
            "reference": row.receipt_number,
            "status": row.status.value,
            "received_at": row.received_at.isoformat(),
        }
        for row in receipts
        if row.status != models.ReceiptStatus.RELEASED
    ][:8]
    quality_control.extend(
        {
            "kind": "hold",
            "id": hold.id,
            "reference": hold.hold_number,
            "status": hold.status.value,
            "target": f"{hold.target_type}:{hold.target_id}",
        }
        for hold in list_quality_holds(db, amo_id=amo_id, limit=8)
    )

    supplier_health = [
        {
            "id": supplier.id,
            "code": supplier.supplier_code,
            "name": supplier.legal_name,
            "status": supplier.status.value,
            "risk_level": supplier.risk_level.value,
            "approval_expiry": min(
                (scope.expires_on for scope in supplier.approval_scopes if scope.expires_on),
                default=None,
            ).isoformat()
            if any(scope.expires_on for scope in supplier.approval_scopes)
            else None,
        }
        for supplier in suppliers
        if supplier.status in {
            models.SupplierLifecycleStatus.RESTRICTED,
            models.SupplierLifecycleStatus.SUSPENDED,
            models.SupplierLifecycleStatus.EXPIRED,
            models.SupplierLifecycleStatus.UNDER_REVIEW,
        }
        or supplier.risk_level in {models.SupplierRiskLevel.HIGH, models.SupplierRiskLevel.CRITICAL}
    ][:8]

    integration_health = {
        "finance_vendor_links": sum(1 for supplier in suppliers if supplier.vendor_id),
        "qms_supplier_links": sum(1 for supplier in suppliers if supplier.qms_supplier_id),
        "inventory_release_gate": "enforced",
        "maintenance_demand_links": db.query(func.count(models.ProcurementRequisition.id)).filter(
            models.ProcurementRequisition.amo_id == amo_id,
            or_(
                models.ProcurementRequisition.work_order_id.isnot(None),
                models.ProcurementRequisition.task_card_id.isnot(None),
                models.ProcurementRequisition.source_module.isnot(None),
            ),
        ).scalar() or 0,
    }

    return schemas.DashboardResponse(
        as_of=datetime.utcnow(),
        counters={key: int(value) for key, value in counters.items()},
        action_queue=action_queue[:10],
        supply_exceptions=supply_exceptions,
        quality_control=quality_control[:10],
        supplier_health=supplier_health,
        integration_health=integration_health,
    )
