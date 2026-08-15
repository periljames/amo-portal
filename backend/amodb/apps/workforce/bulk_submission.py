"""Eligible-only submission wrapper for Workforce contract batches."""
from __future__ import annotations

from sqlalchemy.orm import joinedload

from ..accounts import models as account_models
from . import bulk_contracts, bulk_service, hierarchy_roles, permissions, schemas, services


def submit_contract_batch(db, *, amo_id: str, actor, idempotency_key: str, payload):
    """Snapshot the selected population but queue only records that pass preview rules."""
    selected_ids, selection_token = bulk_service._resolve_checked_selection(
        db, amo_id=amo_id, payload=payload
    )
    override_by_user = {row.user_id: row for row in payload.overrides}
    if set(override_by_user) - set(selected_ids):
        raise ValueError("Contract overrides may only reference selected users")

    users = []
    for chunk in bulk_contracts._chunks(selected_ids):
        users.extend(
            db.query(account_models.User)
            .options(joinedload(account_models.User.department))
            .filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id.in_(chunk),
            )
            .all()
        )
    users_by_id = {str(user.id): user for user in users}
    hire_dates = services.hire_dates_by_user(db, amo_id=amo_id, user_ids=selected_ids)
    eligible_ids: list[str] = []
    item_inputs: dict[str, dict] = {}
    blocked: dict[str, list[str]] = {}

    for user_id in selected_ids:
        user = users_by_id.get(user_id)
        reasons: list[str] = []
        contract_input = bulk_contracts.contract_input_for(
            payload.defaults,
            override_by_user.get(user_id),
            user_id=user_id,
            hire_date=hire_dates.get(user_id),
        )
        try:
            contract = schemas.EmploymentContractCreate.model_validate(contract_input)
        except Exception as exc:
            contract = None
            reasons.append(f"INVALID_CONTRACT: {exc}")
        if user is None:
            reasons.append("USER_NOT_FOUND")
        else:
            if not user.is_active:
                reasons.append("INACTIVE_ACCOUNT")
            if user.is_system_account:
                reasons.append("SYSTEM_ACCOUNT")
        if contract is not None and user is not None:
            if not contract.primary_base_station_id:
                reasons.append("MISSING_PRIMARY_BASE")
            can_have_supervisor = hierarchy_roles.person_can_have_supervisor(
                db,
                amo_id=amo_id,
                user_id=user_id,
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
                        user_id=user_id,
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
            if bulk_contracts._overlap_exists(
                db,
                amo_id=amo_id,
                user_id=user_id,
                effective_from=contract.effective_from,
                effective_to=contract.effective_to,
            ):
                reasons.append("OVERLAPPING_CONTRACT")
        if reasons:
            blocked[user_id] = reasons
            continue
        eligible_ids.append(user_id)
        item_inputs[user_id] = contract_input

    if not eligible_ids:
        raise ValueError("No selected records remain eligible after contract validation")

    row, created = bulk_service._create_operation(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        operation_type="CREATE_CONTRACTS",
        idempotency_key=idempotency_key,
        selection_token=selection_token,
        user_ids=eligible_ids,
        selection_snapshot={
            **payload.selection.model_dump(mode="json"),
            "matched_count": len(selected_ids),
            "eligible_count": len(eligible_ids),
            "blocked_count": len(blocked),
            "blocked_reasons": blocked,
        },
        payload_json={
            "defaults": payload.defaults.model_dump(mode="json"),
            "overrides": [item.model_dump(mode="json") for item in payload.overrides],
        },
        item_inputs=item_inputs,
    )
    return bulk_service._operation_read(row), created
