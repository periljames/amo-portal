from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models, pay_policy, pay_policy_models, permissions, services

router = APIRouter(prefix="/workforce/pay-policy", tags=["workforce-pay-policy"])


class ContractPayPolicyPayload(BaseModel):
    normal_duty_multiplier: Decimal = Field(default=Decimal("1.000"), ge=Decimal("1.000"), max_digits=6, decimal_places=3)
    ordinary_ot_multiplier: Decimal = Field(default=Decimal("1.500"), ge=Decimal("1.500"), max_digits=6, decimal_places=3)
    rest_day_multiplier: Decimal = Field(default=Decimal("2.000"), ge=Decimal("2.000"), max_digits=6, decimal_places=3)
    public_holiday_multiplier: Decimal = Field(default=Decimal("2.000"), ge=Decimal("2.000"), max_digits=6, decimal_places=3)


class ContractPayPolicyRead(ContractPayPolicyPayload):
    contract_id: str


class PayEntitlementRequest(BaseModel):
    classification: pay_policy.DutyPayClassification
    requested_multiplier: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=3)
    contract_id: str | None = None


class PayEntitlementResult(BaseModel):
    classification: pay_policy.DutyPayClassification
    legal_minimum_multiplier: Decimal
    contractual_minimum_multiplier: Decimal
    effective_multiplier: Decimal
    manual_reduction_allowed: bool = False


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _contract(db: Session, *, amo_id: str, contract_id: str) -> models.EmploymentContract:
    row = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.id == contract_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employment contract not found")
    return row


def _policy(db: Session, *, amo_id: str, contract_id: str):
    return db.query(pay_policy_models.EmploymentContractPayPolicy).filter(
        pay_policy_models.EmploymentContractPayPolicy.amo_id == amo_id,
        pay_policy_models.EmploymentContractPayPolicy.contract_id == contract_id,
    ).first()


def _contractual_floor(row, classification: pay_policy.DutyPayClassification) -> Decimal:
    if row is None:
        return pay_policy.minimum_multiplier(classification)
    field = {
        pay_policy.DutyPayClassification.NORMAL_DUTY: "normal_duty_multiplier",
        pay_policy.DutyPayClassification.ORDINARY_OT: "ordinary_ot_multiplier",
        pay_policy.DutyPayClassification.REST_DAY_WORK: "rest_day_multiplier",
        pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK: "public_holiday_multiplier",
    }[classification]
    return pay_policy.minimum_multiplier(classification, contractual_minimum=getattr(row, field))


@router.get("/contracts/{contract_id}", response_model=ContractPayPolicyRead)
def get_contract_pay_policy(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    _contract(db, amo_id=amo_id, contract_id=contract_id)
    permissions.require_permission(db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_VIEW_SENSITIVE)
    row = _policy(db, amo_id=amo_id, contract_id=contract_id)
    if row is None:
        return ContractPayPolicyRead(contract_id=contract_id)
    return ContractPayPolicyRead(
        contract_id=contract_id,
        normal_duty_multiplier=row.normal_duty_multiplier,
        ordinary_ot_multiplier=row.ordinary_ot_multiplier,
        rest_day_multiplier=row.rest_day_multiplier,
        public_holiday_multiplier=row.public_holiday_multiplier,
    )


@router.put("/contracts/{contract_id}", response_model=ContractPayPolicyRead)
def put_contract_pay_policy(
    contract_id: str,
    payload: ContractPayPolicyPayload,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    _contract(db, amo_id=amo_id, contract_id=contract_id)
    permissions.require_permission(db, user=current_user, permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS)
    row = _policy(db, amo_id=amo_id, contract_id=contract_id)
    if row is None:
        row = pay_policy_models.EmploymentContractPayPolicy(
            amo_id=amo_id,
            contract_id=contract_id,
            created_by_user_id=current_user.id,
        )
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.updated_by_user_id = current_user.id
    db.add(row)
    db.commit()
    db.refresh(row)
    return ContractPayPolicyRead(
        contract_id=contract_id,
        normal_duty_multiplier=row.normal_duty_multiplier,
        ordinary_ot_multiplier=row.ordinary_ot_multiplier,
        rest_day_multiplier=row.rest_day_multiplier,
        public_holiday_multiplier=row.public_holiday_multiplier,
    )


@router.post("/validate", response_model=PayEntitlementResult)
def validate_pay_entitlement(
    payload: PayEntitlementRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    legal_minimum = pay_policy.minimum_multiplier(payload.classification)
    policy_row = None
    if payload.contract_id:
        _contract(db, amo_id=amo_id, contract_id=payload.contract_id)
        policy_row = _policy(db, amo_id=amo_id, contract_id=payload.contract_id)
    contractual_minimum = _contractual_floor(policy_row, payload.classification)
    try:
        effective = pay_policy.enforce_multiplier(
            payload.classification,
            requested_multiplier=payload.requested_multiplier,
            contractual_minimum=contractual_minimum,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": str(exc),
                "error_code": "PAY_MULTIPLIER_BELOW_ENTITLEMENT",
                "field_errors": {"requested_multiplier": str(exc)},
                "conflicts": [],
                "retryable": False,
            },
        ) from exc
    return PayEntitlementResult(
        classification=payload.classification,
        legal_minimum_multiplier=legal_minimum,
        contractual_minimum_multiplier=contractual_minimum,
        effective_multiplier=effective,
    )


__all__ = ["router"]
