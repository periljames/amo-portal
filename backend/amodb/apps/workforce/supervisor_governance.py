"""Governed supervisor eligibility and picker queries."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from collections import defaultdict
from types import SimpleNamespace

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import joinedload, lazyload

from ..accounts import models as account_models
from . import governance_models, governance_schemas, hr_people_directory


@dataclass(frozen=True)
class ReportingResolution:
    code: str
    manager_user_id: str | None = None
    candidate_user_ids: tuple[str, ...] = ()


class OrganisationResolver:
    """Request-local, tenant-scoped snapshot of canonical Workforce records.

    Positions supply reporting topology; placements supply dated occupancy and
    explicit supervisor relationships. Account titles and role labels are never
    reporting evidence. Do not cache this snapshot between requests.
    """

    def __init__(self, *, users, positions, units, placements):
        self.users = {str(row.id): row for row in users}
        self.positions = {str(row.id): row for row in positions}
        self.units = {str(row.id): row for row in units}
        self.placements = tuple(placements)
        self.by_user = defaultdict(list)
        self.by_position = defaultdict(list)
        for row in self.placements:
            if (str(row.user_id) in self.users and str(row.position_id) in self.positions
                    and str(row.org_unit_id) in self.units):
                self.by_user[str(row.user_id)].append(row)
                self.by_position[str(row.position_id)].append(row)

    def _unit_path(self, unit_id):
        path = []
        while unit_id is not None:
            unit_id = str(unit_id)
            if unit_id in path or unit_id not in self.units:
                return None
            path.append(unit_id)
            unit_id = self.units[unit_id].parent_id
        return path

    def _resolve_placement(self, row):
        position = self.positions[str(row.position_id)]
        seen = {str(position.id)}
        ancestor = position.reports_to_position_id
        while ancestor:
            if str(ancestor) in seen:
                return ReportingResolution("REPORTING_CYCLE")
            seen.add(str(ancestor))
            parent = self.positions.get(str(ancestor))
            if parent is None:
                return ReportingResolution("REPORTING_POSITION_INACTIVE")
            ancestor = parent.reports_to_position_id
        parent_id = position.reports_to_position_id
        if not parent_id:
            if row.supervisor_user_id:
                return ReportingResolution("REPORTING_RELATIONSHIP_CONFLICT")
            return ReportingResolution("ROOT_POSITION")
        if str(parent_id) not in self.positions:
            return ReportingResolution("REPORTING_POSITION_INACTIVE")
        path = self._unit_path(row.org_unit_id)
        if path is None:
            return ReportingResolution("ORGANISATION_HIERARCHY_INVALID")
        candidates = []
        for holder in self.by_position[str(parent_id)]:
            if str(holder.org_unit_id) not in path:
                continue
            if holder.base_station_id is not None and holder.base_station_id != row.base_station_id:
                continue
            if str(holder.user_id) == str(row.user_id):
                continue
            candidates.append(holder)
        if row.supervisor_user_id:
            selected = [holder for holder in candidates
                        if str(holder.user_id) == str(row.supervisor_user_id)]
            if not selected:
                return ReportingResolution("REPORTING_RELATIONSHIP_CONFLICT")
            candidates = selected
        elif candidates:
            # The closest organisational scope wins; ties remain ambiguous.
            distance = min(path.index(str(holder.org_unit_id)) for holder in candidates)
            candidates = [holder for holder in candidates
                          if path.index(str(holder.org_unit_id)) == distance]
            same_base = [holder for holder in candidates
                         if holder.base_station_id == row.base_station_id]
            if same_base:
                candidates = same_base
        ids = tuple(sorted({str(holder.user_id) for holder in candidates}))
        if len(ids) == 1:
            return ReportingResolution("RESOLVED", ids[0], ids)
        return ReportingResolution("APPROVER_AMBIGUOUS" if ids else "REPORTING_POSITION_VACANT",
                                   candidate_user_ids=ids)

    def direct_manager(self, user_id: str, *, placement_type: str = "PRIMARY"):
        if user_id not in self.users:
            return ReportingResolution("APPOINTMENT_INACTIVE")
        rows = [row for row in self.by_user[user_id] if row.placement_type == placement_type]
        if not rows:
            return ReportingResolution("APPOINTMENT_MISSING")
        if placement_type == "PRIMARY" and len(rows) != 1:
            return ReportingResolution("APPOINTMENT_CONFLICT")
        results = [self._resolve_placement(row) for row in rows]
        if any(result.code not in {"RESOLVED", "ROOT_POSITION"} for result in results):
            return next(result for result in results if result.code not in {"RESOLVED", "ROOT_POSITION"})
        managers = tuple(sorted({result.manager_user_id for result in results if result.manager_user_id}))
        if len(managers) > 1:
            return ReportingResolution("APPROVER_AMBIGUOUS", candidate_user_ids=managers)
        return ReportingResolution("RESOLVED", managers[0], managers) if managers else ReportingResolution("ROOT_POSITION")

    def reporting_chain(self, user_id: str):
        chain = []
        seen = {user_id}
        current = user_id
        while True:
            result = self.direct_manager(current)
            if result.code != "RESOLVED":
                return chain, result.code
            if result.manager_user_id in seen:
                return [], "REPORTING_CYCLE"
            current = result.manager_user_id
            seen.add(current)
            chain.append(current)

    def reports(self, manager_user_id: str, *, indirect: bool = False):
        result = []
        for user_id in sorted(self.by_user):
            chain, code = self.reporting_chain(user_id)
            if code == "REPORTING_CYCLE":
                continue
            if manager_user_id in (chain if indirect else chain[:1]):
                result.append(user_id)
        return result


def organisation_snapshot(db, *, amo_id: str, on_date: date | None = None):
    """Batch-load one tenant; dated occupancy uses the tenant's local date.

    Position and unit topology is current. Historical topology versioning is a
    separate migration requirement; this API must not claim historical topology.
    """
    day = on_date or hr_people_directory._today(db, amo_id=amo_id)
    users = db.query(account_models.User).options(lazyload("*")).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    positions = db.query(governance_models.WorkforcePosition).options(lazyload("*")).filter(
        governance_models.WorkforcePosition.amo_id == amo_id,
        governance_models.WorkforcePosition.is_active.is_(True),
    ).all()
    units = db.query(governance_models.WorkforceOrgUnit).options(lazyload("*")).filter(
        governance_models.WorkforceOrgUnit.amo_id == amo_id,
        governance_models.WorkforceOrgUnit.is_active.is_(True),
    ).all()
    placement = governance_models.WorkforcePersonPlacement
    placements = db.query(placement).options(lazyload("*")).filter(
        placement.amo_id == amo_id, placement.effective_from <= day,
        or_(placement.effective_to.is_(None), placement.effective_to >= day),
    ).all()
    return OrganisationResolver(users=users, positions=positions, units=units, placements=placements)


def lock_organisation(db, *, amo_id: str):
    """Serialize governed hierarchy edits before reading their relationships."""
    row = db.query(account_models.AMO.id).filter(
        account_models.AMO.id == amo_id,
    ).with_for_update().first()
    if row is None:
        raise ValueError("Organisation tenant not found")


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
    lock_organisation(db, amo_id=amo_id)
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
    snapshot = organisation_snapshot(db, amo_id=amo_id, on_date=on_date)
    primary = [row for row in snapshot.by_user[target_user_id] if row.placement_type == "PRIMARY"]
    if len(primary) != 1:
        raise ValueError("Exactly one effective primary appointment is required to assign a reporting manager")
    placement = primary[0]
    proposed = SimpleNamespace(
        position_id=placement.position_id, org_unit_id=placement.org_unit_id,
        base_station_id=placement.base_station_id, user_id=placement.user_id,
        supervisor_user_id=supervisor_user_id,
    )
    resolution = snapshot._resolve_placement(proposed)
    if resolution.code != "RESOLVED" or resolution.manager_user_id != supervisor_user_id:
        raise ValueError("The supervisor must occupy the reporting position in the appointment's organisational and base scope")
    chain, code = snapshot.reporting_chain(supervisor_user_id)
    if code != "ROOT_POSITION" or target_user_id in chain:
        raise ValueError("The supervisor reporting chain is unresolved or would create a cycle")
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
