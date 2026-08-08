from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db
from amodb.security import get_current_active_user

from . import models
from .enums import QMSDomain
from .router import _decorate_car_register_items, router
from .schemas import CAROut, QMSAuditOut, QMSAuditRegisterRowOut, QMSFindingOut


class QMSAuditRegisterPageOut(BaseModel):
    rows: list[QMSAuditRegisterRowOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 25
    offset: int = 0
    has_more: bool = False
    car_linked_findings: int = 0
    open_car_count: int = 0


class QMSCarRegisterSummaryOut(BaseModel):
    total: int = 0
    open: int = 0
    overdue: int = 0
    in_review: int = 0


class QMSCarRegisterPageOut(BaseModel):
    items: list[CAROut] = Field(default_factory=list)
    total: int = 0
    limit: int = 25
    offset: int = 0
    has_more: bool = False
    summary: QMSCarRegisterSummaryOut = Field(default_factory=QMSCarRegisterSummaryOut)


def _normalise_search(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


@router.get("/audits/register/paged", response_model=QMSAuditRegisterPageOut)
def get_audit_register_paged(
    domain: Optional[QMSDomain] = None,
    audit_id: Optional[UUID] = None,
    only_with_cars: bool = False,
    search: Optional[str] = Query(default=None, max_length=160),
    ref: Optional[str] = Query(default=None, max_length=120),
    finding: Optional[str] = Query(default=None, max_length=200),
    audit: Optional[str] = Query(default=None, max_length=200),
    finding_type: Optional[str] = Query(default=None, max_length=80),
    owner: Optional[str] = Query(default=None, max_length=160),
    car: Optional[str] = Query(default=None, max_length=160),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_read_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> QMSAuditRegisterPageOut:
    """Return a bounded tenant-scoped closeout register page."""

    amo_id = str(current_user.amo_id or "").strip()
    if not amo_id:
        return QMSAuditRegisterPageOut(limit=limit, offset=offset)

    Finding = models.QMSAuditFinding
    Audit = models.QMSAudit
    Car = models.CorrectiveActionRequest

    query = (
        db.query(Finding)
        .join(Audit, Audit.id == Finding.audit_id)
        .filter(Audit.amo_id == amo_id)
        .filter(Finding.amo_id == amo_id)
        .filter(Audit.deleted_at.is_(None))
    )

    if domain is not None:
        query = query.filter(Audit.domain == domain)
    if audit_id is not None:
        query = query.filter(Audit.id == audit_id)

    linked_car_exists = (
        db.query(Car.id)
        .filter(Car.amo_id == amo_id, Car.finding_id == Finding.id)
        .exists()
    )
    if only_with_cars:
        query = query.filter(linked_car_exists)

    search_value = _normalise_search(search)
    if search_value:
        like = f"%{search_value}%"
        matching_car_exists = (
            db.query(Car.id)
            .filter(Car.amo_id == amo_id, Car.finding_id == Finding.id)
            .filter(or_(Car.car_number.ilike(like), Car.title.ilike(like), Car.summary.ilike(like)))
            .exists()
        )
        query = query.filter(
            or_(
                Audit.audit_ref.ilike(like),
                Audit.title.ilike(like),
                Finding.finding_ref.ilike(like),
                Finding.description.ilike(like),
                cast(Finding.finding_type, String).ilike(like),
                Finding.acknowledged_by_name.ilike(like),
                matching_car_exists,
            )
        )

    ref_value = _normalise_search(ref)
    if ref_value:
        query = query.filter(Finding.finding_ref.ilike(f"%{ref_value}%"))

    finding_value = _normalise_search(finding)
    if finding_value:
        query = query.filter(Finding.description.ilike(f"%{finding_value}%"))

    audit_value = _normalise_search(audit)
    if audit_value:
        like = f"%{audit_value}%"
        query = query.filter(or_(Audit.audit_ref.ilike(like), Audit.title.ilike(like)))

    type_value = _normalise_search(finding_type)
    if type_value:
        query = query.filter(cast(Finding.finding_type, String).ilike(f"%{type_value}%"))

    owner_value = _normalise_search(owner)
    if owner_value:
        query = query.filter(Finding.acknowledged_by_name.ilike(f"%{owner_value}%"))

    car_value = _normalise_search(car)
    if car_value:
        like = f"%{car_value}%"
        matching_car_exists = (
            db.query(Car.id)
            .filter(Car.amo_id == amo_id, Car.finding_id == Finding.id)
            .filter(or_(Car.car_number.ilike(like), Car.title.ilike(like), Car.summary.ilike(like)))
            .exists()
        )
        query = query.filter(matching_car_exists)

    total = int(query.order_by(None).count())

    filtered_ids = query.with_entities(Finding.id).subquery()
    filtered_id_query = db.query(filtered_ids.c.id)
    car_linked_findings = int(
        db.query(func.count(func.distinct(Car.finding_id)))
        .filter(Car.amo_id == amo_id)
        .filter(Car.finding_id.in_(filtered_id_query))
        .scalar()
        or 0
    )
    open_car_count = int(
        db.query(func.count(Car.id))
        .filter(Car.amo_id == amo_id)
        .filter(Car.finding_id.in_(filtered_id_query))
        .filter(Car.status != models.CARStatus.CLOSED)
        .filter(Car.status != models.CARStatus.CANCELLED)
        .scalar()
        or 0
    )

    page_records = (
        query.add_entity(Audit)
        .order_by(Audit.audit_ref.asc(), Finding.created_at.desc(), Finding.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    finding_ids = [finding_row.id for finding_row, _audit_row in page_records]
    cars_by_finding: dict[UUID, list[models.CorrectiveActionRequest]] = {finding_id: [] for finding_id in finding_ids}
    if finding_ids:
        linked_cars = (
            db.query(Car)
            .filter(Car.amo_id == amo_id, Car.finding_id.in_(finding_ids))
            .order_by(Car.created_at.asc(), Car.id.asc())
            .all()
        )
        for linked_car in linked_cars:
            cars_by_finding.setdefault(linked_car.finding_id, []).append(linked_car)

    rows = [
        QMSAuditRegisterRowOut(
            audit=QMSAuditOut.model_validate(audit_row),
            finding=QMSFindingOut.model_validate(finding_row),
            linked_cars=[CAROut.model_validate(item) for item in cars_by_finding.get(finding_row.id, [])],
        )
        for finding_row, audit_row in page_records
    ]

    return QMSAuditRegisterPageOut(
        rows=rows,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(rows) < total,
        car_linked_findings=car_linked_findings,
        open_car_count=open_car_count,
    )


CarRegisterScope = Literal[
    "all",
    "active",
    "overdue",
    "due_soon",
    "awaiting_auditee",
    "awaiting_quality_review",
    "awaiting_effectiveness_review",
    "closed",
]


@router.get("/cars/register/paged", response_model=QMSCarRegisterPageOut)
def get_car_register_paged(
    program: Optional[models.CARProgram] = None,
    status_: Optional[models.CARStatus] = None,
    scope: CarRegisterScope = "all",
    car_id: Optional[UUID] = None,
    assigned_to_user_id: Optional[str] = Query(default=None, max_length=36),
    audit_id: Optional[UUID] = None,
    search: Optional[str] = Query(default=None, max_length=160),
    due_soon_days: int = Query(default=30, ge=0, le=90),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_read_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> QMSCarRegisterPageOut:
    """Return a bounded CAR register page with server-side workflow scopes."""

    amo_id = str(current_user.amo_id or "").strip()
    if not amo_id:
        return QMSCarRegisterPageOut(limit=limit, offset=offset)

    Car = models.CorrectiveActionRequest
    Finding = models.QMSAuditFinding
    Audit = models.QMSAudit
    today = date.today()
    active_statuses = [
        models.CARStatus.DRAFT,
        models.CARStatus.OPEN,
        models.CARStatus.IN_PROGRESS,
        models.CARStatus.PENDING_VERIFICATION,
        models.CARStatus.ESCALATED,
    ]
    auditee_statuses = [
        models.CARStatus.OPEN,
        models.CARStatus.IN_PROGRESS,
        models.CARStatus.ESCALATED,
    ]

    base_scope = db.query(Car).filter(Car.amo_id == amo_id)
    if program is not None:
        base_scope = base_scope.filter(Car.program == program)

    summary_total = int(base_scope.order_by(None).count())
    summary_open = int(base_scope.filter(Car.status.in_(active_statuses)).order_by(None).count())
    summary_overdue = int(
        base_scope.filter(Car.status.in_(active_statuses), Car.due_date.isnot(None), Car.due_date < today)
        .order_by(None)
        .count()
    )
    summary_review = int(
        base_scope.filter(Car.status.in_(active_statuses))
        .filter(
            or_(
                Car.status == models.CARStatus.PENDING_VERIFICATION,
                Car.root_cause_status == "SUBMITTED",
                Car.capa_status == "SUBMITTED",
            )
        )
        .order_by(None)
        .count()
    )

    query = (
        base_scope.outerjoin(
            Finding,
            and_(Finding.id == Car.finding_id, Finding.amo_id == amo_id),
        )
        .outerjoin(
            Audit,
            and_(Audit.id == Finding.audit_id, Audit.amo_id == amo_id, Audit.deleted_at.is_(None)),
        )
    )

    if status_ is not None:
        query = query.filter(Car.status == status_)
    if car_id is not None:
        query = query.filter(Car.id == car_id)
    assigned_value = _normalise_search(assigned_to_user_id)
    if assigned_value:
        query = query.filter(Car.assigned_to_user_id == assigned_value)
    if audit_id is not None:
        query = query.filter(Finding.audit_id == audit_id)

    if scope == "active":
        query = query.filter(Car.status.in_(active_statuses))
    elif scope == "overdue":
        query = query.filter(Car.status.in_(active_statuses), Car.due_date.isnot(None), Car.due_date < today)
    elif scope == "due_soon":
        query = query.filter(
            Car.status.in_(active_statuses),
            Car.due_date.isnot(None),
            Car.due_date >= today,
            Car.due_date <= today + timedelta(days=due_soon_days),
        )
    elif scope == "awaiting_auditee":
        query = query.filter(Car.status.in_(auditee_statuses)).filter(
            or_(
                Car.submitted_at.is_(None),
                Car.root_cause_status == "REJECTED",
                Car.capa_status.in_(["REJECTED", "NEEDS_EVIDENCE"]),
            )
        )
    elif scope == "awaiting_quality_review":
        query = query.filter(Car.status.in_(active_statuses)).filter(
            or_(Car.root_cause_status == "SUBMITTED", Car.capa_status == "SUBMITTED")
        )
    elif scope == "awaiting_effectiveness_review":
        query = query.filter(Car.status == models.CARStatus.PENDING_VERIFICATION)
    elif scope == "closed":
        query = query.filter(Car.status == models.CARStatus.CLOSED)

    search_value = _normalise_search(search)
    if search_value:
        like = f"%{search_value}%"
        query = query.filter(
            or_(
                Car.car_number.ilike(like),
                Car.title.ilike(like),
                Car.summary.ilike(like),
                cast(Car.status, String).ilike(like),
                cast(Car.priority, String).ilike(like),
                Car.submitted_by_name.ilike(like),
                Finding.finding_ref.ilike(like),
                Finding.description.ilike(like),
                Audit.audit_ref.ilike(like),
                Audit.title.ilike(like),
            )
        )

    total = int(query.order_by(None).count())
    items = (
        query.order_by(Car.created_at.desc(), Car.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    decorated = _decorate_car_register_items(db, items)

    return QMSCarRegisterPageOut(
        items=[CAROut.model_validate(item) for item in decorated],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(decorated) < total,
        summary=QMSCarRegisterSummaryOut(
            total=summary_total,
            open=summary_open,
            overdue=summary_overdue,
            in_review=summary_review,
        ),
    )
