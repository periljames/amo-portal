"""Governed supervisor eligibility and picker queries."""
from __future__ import annotations

import math

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import joinedload

from ..accounts import models as account_models
from . import governance_models, governance_schemas, hr_people_directory


def _supervisory_placement_exists(*, amo_id: str, today):
    placement = governance_models.WorkforcePersonPlacement
    position = governance_models.WorkforcePosition
    return exists().where(
        placement.amo_id == amo_id,
        placement.user_id == account_models.User.id,
        placement.placement_type == "PRIMARY",
        placement.effective_from <= today,
        or_(placement.effective_to.is_(None), placement.effective_to >= today),
        position.id == placement.position_id,
        position.amo_id == amo_id,
        position.is_active.is_(True),
        position.is_supervisory.is_(True),
    )


def require_supervisor(db, *, amo_id: str, supervisor_user_id: str, target_user_id: str, on_date):
    if supervisor_user_id == target_user_id:
        raise ValueError("A person cannot supervise themselves")
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == supervisor_user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
        hr_people_directory._effective_contract_exists(amo_id=amo_id, today=on_date),
        _supervisory_placement_exists(amo_id=amo_id, today=on_date),
    ).first()
    if user is None:
        raise ValueError(
            "The selected supervisor must be an active tenant user with an effective contract and an active supervisory position on the effective date"
        )
    return user


def list_supervisors(
    db,
    *,
    amo_id: str,
    page: int,
    page_size: int,
    search: str | None = None,
    org_unit_id: str | None = None,
    exclude_user_id: str | None = None,
):
    from . import governance_directory

    today = governance_directory._today(db, amo_id=amo_id)
    query = governance_directory._human_query(db, amo_id=amo_id).filter(
        hr_people_directory._effective_contract_exists(amo_id=amo_id, today=today),
        _supervisory_placement_exists(amo_id=amo_id, today=today),
    )
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            account_models.User.full_name.ilike(term),
            account_models.User.staff_code.ilike(term),
            account_models.User.position_title.ilike(term),
        ))
    if exclude_user_id:
        query = query.filter(account_models.User.id != exclude_user_id)
    if org_unit_id:
        org_ids = governance_directory.descendant_ids(db, amo_id=amo_id, org_unit_id=org_unit_id)
        placement = governance_models.WorkforcePersonPlacement
        query = query.filter(exists().where(
            placement.amo_id == amo_id,
            placement.user_id == account_models.User.id,
            placement.placement_type == "PRIMARY",
            placement.org_unit_id.in_(org_ids),
            placement.effective_from <= today,
            or_(placement.effective_to.is_(None), placement.effective_to >= today),
        ))

    total = int(query.order_by(None).count())
    safe_size = max(1, min(int(page_size), 100))
    pages = math.ceil(total / safe_size) if total else 0
    safe_page = min(max(1, int(page)), pages or 1)
    users = query.order_by(
        account_models.User.full_name.asc(), account_models.User.id.asc()
    ).offset((safe_page - 1) * safe_size).limit(safe_size).all()
    user_ids = [str(user.id) for user in users]
    placements = db.query(governance_models.WorkforcePersonPlacement).options(
        joinedload(governance_models.WorkforcePersonPlacement.org_unit),
        joinedload(governance_models.WorkforcePersonPlacement.position),
    ).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.user_id.in_(user_ids or ["__none__"]),
        governance_models.WorkforcePersonPlacement.placement_type == "PRIMARY",
        governance_models.WorkforcePersonPlacement.effective_from <= today,
        or_(
            governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= today,
        ),
    ).order_by(
        governance_models.WorkforcePersonPlacement.effective_from.desc(),
        governance_models.WorkforcePersonPlacement.id.asc(),
    ).all()
    primary = {}
    for row in placements:
        primary.setdefault(str(row.user_id), row)
    return governance_schemas.SupervisorOptionsPage(
        items=[governance_schemas.SupervisorOption(
            user_id=str(user.id),
            staff_code=user.staff_code,
            full_name=user.full_name,
            position_title=getattr(getattr(primary.get(str(user.id)), "position", None), "canonical_title", None)
                or user.position_title,
            org_unit_name=getattr(getattr(primary.get(str(user.id)), "org_unit", None), "name", None),
            is_supervisory_position=True,
        ) for user in users],
        page=safe_page,
        page_size=safe_size,
        total=total,
        pages=pages,
    )
