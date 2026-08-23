"""Validation and per-person execution for Workforce bulk actions."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..accounts import models as account_models
from . import (
    bulk_models,
    bulk_schemas,
    hierarchy_roles,
    hr_selection_integrity,
    models,
    permissions,
    schemas,
    services,
)

MAX_BULK_RECORDS = 10_000
QUERY_CHUNK_SIZE = 500


def _chunks(values: list[str], size: int = QUERY_CHUNK_SIZE) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def contract_input_for(
    defaults: bulk_schemas.ContractDefaults,
    override: bulk_schemas.ContractOverride | None,
    *,
    user_id: str,
    hire_date: date | None = None,
) -> dict[str, Any]:
    data = defaults.model_dump(mode="json")
    if override is not None:
        for key, value in override.model_dump(mode="json", exclude={"user_id"}).items():
            if value is not None:
                data[key] = value
    data["user_id"] = user_id
    if hire_date is not None:
        data["effective_from"] = hire_date.isoformat()
    return data


def _overlap_exists(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    effective_from: date,
    effective_to: date | None,
) -> bool:
    end = effective_to or date.max
    return db.query(models.EmploymentContract.id).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.employment_status.in_([
            models.EmploymentStatus.ACTIVE,
            models.EmploymentStatus.ONBOARDING,
            models.EmploymentStatus.SUSPENDED,
        ]),
        models.EmploymentContract.effective_from <= end,
        or_(
            models.EmploymentContract.effective_to.is_(None),
            models.EmploymentContract.effective_to >= effective_from,
        ),
    ).first() is not None


def preview_contract_batch(
    db: Session,
    *,
    amo_id: str,
    actor: account_models.User,
    payload: bulk_schemas.ContractBatchPreviewRequest,
) -> bulk_schemas.ContractBatchPreview:
    user_ids, selection_token = hr_selection_integrity.resolve_with_token(
        db, amo_id=amo_id, selection=payload.selection
    )
    if len(user_ids) > MAX_BULK_RECORDS:
        raise ValueError(f"Bulk operations are limited to {MAX_BULK_RECORDS:,} records")

    override_by_user = {row.user_id: row for row in payload.overrides}
    if set(override_by_user) - set(user_ids):
        raise ValueError("Contract overrides may only reference selected users")

    users: list[account_models.User] = []
    for chunk in _chunks(user_ids):
        users.extend(
            db.query(account_models.User)
            .options(joinedload(account_models.User.department))
            .filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id.in_(chunk),
            )
            .all()
        )
    users.sort(key=lambda row: ((row.full_name or "").lower(), str(row.id)))
    hire_dates = services.hire_dates_by_user(
        db, amo_id=amo_id, user_ids=[str(user.id) for user in users]
    )

    rows: list[bulk_schemas.ContractPreviewRow] = []
    eligible_count = 0
    already_contracted_count = 0
    for user in users:
        reasons: list[str] = []
        contract_input = contract_input_for(
            payload.defaults,
            override_by_user.get(str(user.id)),
            user_id=str(user.id),
            hire_date=hire_dates.get(str(user.id)),
        )
        try:
            contract = schemas.EmploymentContractCreate.model_validate(contract_input)
        except Exception as exc:
            contract = None
            reasons.append(f"INVALID_CONTRACT: {exc}")

        if not user.is_active:
            reasons.append("INACTIVE_ACCOUNT")
        if user.is_system_account:
            reasons.append("SYSTEM_ACCOUNT")
        if contract is not None:
            if not contract.primary_base_station_id:
                reasons.append("MISSING_PRIMARY_BASE")
            can_have_supervisor = hierarchy_roles.person_can_have_supervisor(
                db,
                amo_id=amo_id,
                user_id=str(user.id),
                on_date=services._supervisor_validation_date(
                    effective_from=contract.effective_from,
                    effective_to=contract.effective_to,
                ),
            )
            if can_have_supervisor and contract.supervisor_user_id is None:
                reasons.append("MISSING_SUPERVISOR")
            if not can_have_supervisor and contract.supervisor_user_id is not None:
                reasons.append("MANAGEMENT_POSITION_CANNOT_HAVE_SUPERVISOR")
            if can_have_supervisor and contract.supervisor_user_id:
                try:
                    hierarchy_roles.require_no_reporting_cycle(
                        db,
                        amo_id=amo_id,
                        user_id=str(user.id),
                        supervisor_user_id=contract.supervisor_user_id,
                        on_date=services._supervisor_validation_date(
                            effective_from=contract.effective_from,
                            effective_to=contract.effective_to,
                        ),
                    )
                except ValueError as exc:
                    reasons.append(f"INVALID_REPORTING_LINE: {exc}")
            if not permissions.has_permission(
                db,
                user=actor,
                permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
                department_id=user.department_id,
                base_station_id=contract.primary_base_station_id,
            ):
                reasons.append("OUTSIDE_PERMISSION_SCOPE")
            if _overlap_exists(
                db,
                amo_id=amo_id,
                user_id=str(user.id),
                effective_from=contract.effective_from,
                effective_to=contract.effective_to,
            ):
                reasons.append("OVERLAPPING_CONTRACT")
                already_contracted_count += 1

        eligible = not reasons
        eligible_count += int(eligible)
        if len(rows) < payload.preview_limit:
            rows.append(
                bulk_schemas.ContractPreviewRow(
                    user_id=str(user.id),
                    staff_code=user.staff_code,
                    full_name=user.full_name or user.email or str(user.id),
                    department_name=getattr(user.department, "name", None),
                    position_title=user.position_title,
                    primary_base_station_id=(
                        contract.primary_base_station_id
                        if contract else contract_input.get("primary_base_station_id")
                    ),
                    supervisor_user_id=(
                        contract.supervisor_user_id
                        if contract else contract_input.get("supervisor_user_id")
                    ),
                    effective_from=(contract.effective_from if contract else hire_dates.get(str(user.id)) or payload.defaults.effective_from),
                    effective_to=(contract.effective_to if contract else payload.defaults.effective_to),
                    eligible=eligible,
                    reasons=reasons,
                )
            )

    return bulk_schemas.ContractBatchPreview(
        selection_token=selection_token,
        matched_count=len(user_ids),
        eligible_count=eligible_count,
        blocked_count=len(user_ids) - eligible_count,
        already_contracted_count=already_contracted_count,
        rows=rows,
        rows_truncated=len(user_ids) > len(rows),
    )


def process_contract_item(
    db: Session,
    *,
    operation: bulk_models.WorkforceBulkOperation,
    item: bulk_models.WorkforceBulkOperationItem,
    actor: account_models.User,
) -> tuple[str, str, str, dict[str, Any] | None]:
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == operation.amo_id,
        account_models.User.id == item.user_id,
    ).first()
    if user is None:
        return "FAILED", "USER_NOT_FOUND", "The selected user no longer exists in this tenant", None
    if not user.is_active or user.is_system_account:
        return "SKIPPED", "ACCOUNT_INELIGIBLE", "Inactive and system accounts cannot receive employment contracts", None

    contract_payload = schemas.EmploymentContractCreate.model_validate(item.input_json or {})
    if not permissions.has_permission(
        db,
        user=actor,
        permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
        department_id=user.department_id,
        base_station_id=contract_payload.primary_base_station_id,
    ):
        return "FAILED", "OUTSIDE_PERMISSION_SCOPE", "The administrator is not authorized for this person's department or base", None
    try:
        row = services.create_contract(
            db,
            amo_id=operation.amo_id,
            actor_user_id=operation.actor_user_id,
            payload=contract_payload,
        )
    except ValueError as exc:
        if "overlaps existing contract" in str(exc):
            return "SKIPPED", "OVERLAPPING_CONTRACT", str(exc), None
        raise
    return "SUCCEEDED", "CONTRACT_CREATED", "Employment contract created", {"contract_id": str(row.id)}


def process_default_pattern_item(
    db: Session,
    *,
    operation: bulk_models.WorkforceBulkOperation,
    item: bulk_models.WorkforceBulkOperationItem,
    actor: account_models.User,
) -> tuple[str, str, str, dict[str, Any] | None]:
    from .retired_pattern_guard import RETIRED_DEFAULT_PATTERN_MESSAGE

    return (
        "FAILED",
        "DEFAULT_PATTERN_RETIRED",
        RETIRED_DEFAULT_PATTERN_MESSAGE,
        None,
    )
