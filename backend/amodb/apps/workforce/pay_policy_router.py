from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...security import get_current_active_user
from ..accounts import models as account_models
from . import pay_policy

router = APIRouter(prefix="/workforce/pay-policy", tags=["workforce-pay-policy"])


class PayEntitlementRequest(BaseModel):
    classification: pay_policy.DutyPayClassification
    requested_multiplier: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=3)


class PayEntitlementResult(BaseModel):
    classification: pay_policy.DutyPayClassification
    legal_minimum_multiplier: Decimal
    effective_multiplier: Decimal
    manual_reduction_allowed: bool = False


@router.post("/validate", response_model=PayEntitlementResult)
def validate_pay_entitlement(
    payload: PayEntitlementRequest,
    current_user: account_models.User = Depends(get_current_active_user),
):
    # Authentication is intentional even though this resolver is read-only: it
    # is an operational payroll policy endpoint, not a public rate calculator.
    del current_user
    legal_minimum = pay_policy.minimum_multiplier(payload.classification)
    try:
        effective = pay_policy.enforce_multiplier(
            payload.classification,
            requested_multiplier=payload.requested_multiplier,
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
        effective_multiplier=effective,
    )


__all__ = ["router"]
