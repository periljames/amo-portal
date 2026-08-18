from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from . import pay_policy, pay_policy_models


FIELD_BY_CLASSIFICATION = {
    pay_policy.DutyPayClassification.NORMAL_DUTY: "normal_duty_multiplier",
    pay_policy.DutyPayClassification.ORDINARY_OT: "ordinary_ot_multiplier",
    pay_policy.DutyPayClassification.REST_DAY_WORK: "rest_day_multiplier",
    pay_policy.DutyPayClassification.PUBLIC_HOLIDAY_WORK: "public_holiday_multiplier",
}


def attach_contract_pay_policies(db: Session, *, amo_id: str, contracts_by_user: dict) -> dict:
    contracts = [contract for rows in contracts_by_user.values() for contract in rows]
    if not contracts:
        return contracts_by_user
    by_contract = {
        str(row.contract_id): row
        for row in db.query(pay_policy_models.EmploymentContractPayPolicy).filter(
            pay_policy_models.EmploymentContractPayPolicy.amo_id == amo_id,
            pay_policy_models.EmploymentContractPayPolicy.contract_id.in_([str(row.id) for row in contracts]),
        ).all()
    }
    for contract in contracts:
        policy = by_contract.get(str(contract.id))
        if policy is None:
            continue
        for field in FIELD_BY_CLASSIFICATION.values():
            setattr(contract, field, getattr(policy, field))
    return contracts_by_user


def install_timesheet_policy(timesheet_module) -> None:
    if getattr(timesheet_module, "_contract_pay_store_installed", False):
        return
    original = timesheet_module._contracts_by_user

    def governed_contracts_by_user(db: Session, *, amo_id: str, user_ids, period_start, period_end):
        result = original(
            db,
            amo_id=amo_id,
            user_ids=user_ids,
            period_start=period_start,
            period_end=period_end,
        )
        return attach_contract_pay_policies(db, amo_id=amo_id, contracts_by_user=result)

    timesheet_module._contracts_by_user = governed_contracts_by_user
    timesheet_module._contract_pay_store_installed = True


def contractual_floor(policy_row, classification: pay_policy.DutyPayClassification) -> Decimal:
    return Decimal(str(getattr(policy_row, FIELD_BY_CLASSIFICATION[classification])))
