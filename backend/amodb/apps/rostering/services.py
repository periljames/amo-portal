# backend/amodb/apps/rostering/services.py
"""Public service facade for the complete duty-rostering domain.

The implementation is split by responsibility to keep lifecycle, assignment,
planning and reporting logic independently testable. Import service functions
from this module when compatibility with the original Phase 1 import path is
required.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..quality import models as quality_models
from ..training import models as training_models
from ..work import models as work_models
from ..workforce import calculations as workforce_calculations
from ..workforce import models as workforce_models
from ..workforce import services as workforce_services
from . import assignments, catalog, commitments, common, governance, lifecycle, models, planning, reports, schemas
from .aircraft_allocation import RosterAircraftAllocation
from .assignments import (
    allocate_to_task,
    bulk_create_assignments as _bulk_create_assignments,
    create_assignment as _create_assignment,
    delete_assignment,
    delete_task_link,
    generate_from_patterns as _generate_from_patterns,
    link_task_assignment,
    list_assignments,
    list_task_links,
    serialize_task_link,
    update_assignment as _update_assignment,
)
from .catalog import (
    create_demand_requirement,
    create_period,
    create_rule,
    create_shift_template,
    create_version,
    list_demand_requirements,
    list_periods,
    list_rules,
    list_shift_templates as _list_shift_templates,
    list_versions,
    retire_demand_requirement,
    roster_contracts,
    seed_default_shift_templates,
    update_period,
    update_rule,
    update_shift_template,
)
from .common import (
    assignment_hours,
    can_approve_roster,
    can_manage_roster,
    can_view_roster,
    effective_amo_id,
    get_assignment,
    get_period,
    get_version,
    serialize_assignment,
    serialize_finding,
    serialize_period,
    serialize_version,
    task_link_hours,
)
from .lifecycle import (
    acknowledge_version,
    approve_version,
    list_exceptions,
    override_finding,
    publish_version,
    revoke_exception,
    submit_version,
    validate_version,
)
from .planning import dashboard, my_roster, planning_board, published_assignments
from .reports import assignment_export_rows, report_summary


def get_effective_amo_id(user: account_models.User) -> str:
    return effective_amo_id(user)


def list_shift_templates(db: Session, *, amo_id: str, include_inactive: bool = False):
    """Return tenant templates while repairing the historical TRAIN semantic.

    Training occupies an employee's working time and must participate in duty,
    overlap, rest and timesheet calculations. Earlier seeds marked the default
    TRAIN template as non-duty; reconcile it whenever templates are loaded so
    both upgraded and newly provisioned tenants receive the canonical meaning.
    """
    rows = _list_shift_templates(db, amo_id=amo_id, include_inactive=include_inactive)
    for row in rows:
        if row.code == "TRAIN" and not row.counts_as_duty:
            row.counts_as_duty = True
            db.add(row)
    db.flush()
    return rows


def _value(value) -> str:
    return str(getattr(value, "value", value))


def _ensure_source_owned_state(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    starts_at,
    ends_at,
    assignment_status,
    assignment_source,
    source_reference_id: Optional[str],
    version_id: Optional[str] = None,
    exclude_assignment_id: Optional[str] = None,
) -> None:
    """Protect canonical Workforce, Training and Quality state at mutation time."""
    status_value = _value(assignment_status)
    source_value = _value(assignment_source)
    external_state = status_value in {"LEAVE", "TRAINING", "UNAVAILABLE"}
    trusted_external_source = source_value in {"LEAVE", "TRAINING", "SYSTEM"} and bool(source_reference_id)
    if external_state and not trusted_external_source:
        owner = "Training" if status_value == "TRAINING" else "Workforce"
        raise ValueError(
            f"{status_value.replace('_', ' ').title()} is owned by the {owner} module. "
            "Create or approve it there; Rostering will display it automatically."
        )

    if trusted_external_source or status_value in {"OFF", "LEAVE", "TRAINING", "UNAVAILABLE"}:
        return

    if version_id:
        collision_query = db.query(models.RosterAssignment).filter(
            models.RosterAssignment.amo_id == amo_id,
            models.RosterAssignment.version_id == version_id,
            models.RosterAssignment.user_id == user_id,
            models.RosterAssignment.deleted_at.is_(None),
            models.RosterAssignment.status.in_([
                models.RosterAssignmentStatus.DUTY,
                models.RosterAssignmentStatus.STANDBY,
                models.RosterAssignmentStatus.TRAVEL,
                models.RosterAssignmentStatus.OTHER,
            ]),
            models.RosterAssignment.starts_at < ends_at,
            models.RosterAssignment.ends_at > starts_at,
        )
        if exclude_assignment_id:
            collision_query = collision_query.filter(models.RosterAssignment.id != exclude_assignment_id)
        collision = collision_query.order_by(models.RosterAssignment.starts_at.asc(), models.RosterAssignment.id.asc()).first()
        if collision:
            raise ValueError(
                "This person already has an overlapping roster assignment "
                f"({collision.starts_at.isoformat()} to {collision.ends_at.isoformat()}). "
                "Move, shorten or remove the existing duty before using this period."
            )

    final_date = (ends_at - timedelta(microseconds=1)).date()
    start_contract = workforce_services.active_contract_for_user(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=starts_at.date(),
    )
    end_contract = workforce_services.active_contract_for_user(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=final_date,
    )
    if not start_contract or not end_contract:
        raise ValueError(
            "This person has no active employment contract for the selected duty period. "
            "Inactive, suspended, terminated and out-of-contract personnel cannot be rostered."
        )

    availability = db.query(workforce_models.EmployeeAvailabilityEvent.id).filter(
        workforce_models.EmployeeAvailabilityEvent.amo_id == amo_id,
        workforce_models.EmployeeAvailabilityEvent.user_id == user_id,
        workforce_models.EmployeeAvailabilityEvent.blocking.is_(True),
        workforce_models.EmployeeAvailabilityEvent.starts_at < ends_at,
        workforce_models.EmployeeAvailabilityEvent.ends_at > starts_at,
    ).first()
    if availability:
        raise ValueError(
            "This person has blocking leave or unavailability in the selected period. "
            "Resolve the Workforce source record before assigning duty."
        )

    pending_leave = db.query(workforce_models.LeaveRequest.id).filter(
        workforce_models.LeaveRequest.amo_id == amo_id,
        workforce_models.LeaveRequest.user_id == user_id,
        workforce_models.LeaveRequest.status.in_([
            workforce_models.LeaveRequestStatus.SUBMITTED,
            workforce_models.LeaveRequestStatus.SUPERVISOR_APPROVED,
        ]),
        workforce_models.LeaveRequest.starts_at < ends_at,
        workforce_models.LeaveRequest.ends_at > starts_at,
    ).first()
    if pending_leave:
        raise ValueError(
            "This person has a pending leave request in the selected period. "
            "The dates stay protected until Workforce approves or rejects it."
        )

    training = db.query(training_models.TrainingEventParticipant.id).join(
        training_models.TrainingEvent,
        training_models.TrainingEventParticipant.event_id == training_models.TrainingEvent.id,
    ).filter(
        training_models.TrainingEventParticipant.amo_id == amo_id,
        training_models.TrainingEventParticipant.user_id == user_id,
        training_models.TrainingEventParticipant.status.notin_([
            training_models.TrainingParticipantStatus.CANCELLED,
            training_models.TrainingParticipantStatus.NO_SHOW,
            training_models.TrainingParticipantStatus.DEFERRED,
        ]),
        training_models.TrainingEvent.status != training_models.TrainingEventStatus.CANCELLED,
        training_models.TrainingEvent.starts_on <= final_date,
        or_(
            training_models.TrainingEvent.ends_on.is_(None),
            training_models.TrainingEvent.ends_on >= starts_at.date(),
        ),
    ).first()
    if training:
        raise ValueError(
            "This person is already scheduled for Training in the selected period. "
            "The Training commitment is shown automatically and cannot be overwritten by duty."
        )

    quality_audit = db.query(quality_models.QMSAudit.id).filter(
        quality_models.QMSAudit.amo_id == amo_id,
        quality_models.QMSAudit.deleted_at.is_(None),
        quality_models.QMSAudit.status != quality_models.QMSAuditStatus.CLOSED,
        quality_models.QMSAudit.planned_start.isnot(None),
        quality_models.QMSAudit.planned_start <= final_date,
        or_(
            quality_models.QMSAudit.planned_end.is_(None),
            quality_models.QMSAudit.planned_end >= starts_at.date(),
        ),
        or_(
            quality_models.QMSAudit.lead_auditor_user_id == user_id,
            quality_models.QMSAudit.observer_auditor_user_id == user_id,
            quality_models.QMSAudit.assistant_auditor_user_id == user_id,
            quality_models.QMSAudit.auditee_user_id == user_id,
        ),
    ).first()
    if quality_audit:
        raise ValueError(
            "This person is assigned to a Quality audit in the selected period. "
            "The QMS commitment is shown automatically and cannot be overwritten by duty."
        )


def create_assignment(db: Session, *, version, actor_user_id: str, payload):
    _ensure_source_owned_state(
        db,
        amo_id=version.amo_id,
        user_id=payload.user_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        assignment_status=payload.status,
        assignment_source=payload.source,
        source_reference_id=payload.source_reference_id,
        version_id=getattr(version, "id", None),
    )
    return _create_assignment(db, version=version, actor_user_id=actor_user_id, payload=payload)


def update_assignment(db: Session, *, row, actor_user_id: str, payload):
    fields = common.model_fields_set(payload)
    _ensure_source_owned_state(
        db,
        amo_id=row.amo_id,
        user_id=row.user_id,
        starts_at=payload.starts_at if "starts_at" in fields else row.starts_at,
        ends_at=payload.ends_at if "ends_at" in fields else row.ends_at,
        assignment_status=payload.status if "status" in fields else row.status,
        assignment_source=row.source,
        source_reference_id=row.source_reference_id,
        version_id=row.version_id,
        exclude_assignment_id=row.id,
    )
    return _update_assignment(db, row=row, actor_user_id=actor_user_id, payload=payload)


def _remap_bulk_indexes(entries: list[dict], index_map: list[int]) -> list[dict]:
    remapped: list[dict] = []
    for entry in entries:
        item = dict(entry)
        filtered_index = item.get("index")
        if isinstance(filtered_index, int) and 0 <= filtered_index < len(index_map):
            item["index"] = index_map[filtered_index]
        remapped.append(item)
    return remapped


def bulk_create_assignments(db: Session, *, version, actor_user_id: str, payload):
    """Apply the same source-of-truth guard to bulk and pattern assignments."""
    valid_items = []
    index_map: list[int] = []
    preflight_conflicts: list[dict] = []
    pending_busy: dict[str, list] = {}

    for index, item in enumerate(payload.assignments):
        try:
            _ensure_source_owned_state(
                db,
                amo_id=version.amo_id,
                user_id=item.user_id,
                starts_at=item.starts_at,
                ends_at=item.ends_at,
                assignment_status=item.status,
                assignment_source=item.source,
                source_reference_id=item.source_reference_id,
                version_id=getattr(version, "id", None),
            )
            if _value(item.status) in {"DUTY", "STANDBY", "TRAVEL", "OTHER"}:
                pending_collision = next((
                    row for row in pending_busy.get(item.user_id, [])
                    if _interval_overlaps(item.starts_at, item.ends_at, row.starts_at, row.ends_at)
                ), None)
                if pending_collision:
                    raise ValueError(
                        "Bulk input contains overlapping duty for the same person. "
                        "Correct the work pattern or source rows before generating the roster."
                    )
                pending_busy.setdefault(item.user_id, []).append(item)
        except ValueError as exc:
            conflict = {
                "index": index,
                "client_id": getattr(item, "client_id", None),
                "reason": str(exc),
            }
            if payload.atomic:
                raise ValueError(f"Bulk assignment failed at item {index}: {exc}") from exc
            preflight_conflicts.append(conflict)
            continue
        valid_items.append(item)
        index_map.append(index)

    guarded_payload = payload.model_copy(update={"assignments": valid_items})
    result = _bulk_create_assignments(
        db,
        version=version,
        actor_user_id=actor_user_id,
        payload=guarded_payload,
    )
    result.skipped = _remap_bulk_indexes(result.skipped, index_map)
    result.conflicts = preflight_conflicts + _remap_bulk_indexes(result.conflicts, index_map)
    return result


# Pattern generation resolves this module-global function at call time. Rebind
# it once so generated rows cannot bypass the same Workforce/Training/QMS guard.
assignments.bulk_create_assignments = bulk_create_assignments


def generate_from_patterns(db: Session, *, version, actor_user_id: str, payload):
    return _generate_from_patterns(
        db,
        version=version,
        actor_user_id=actor_user_id,
        payload=payload,
    )


_BUSY_ASSIGNMENT_STATUSES = {
    models.RosterAssignmentStatus.DUTY,
    models.RosterAssignmentStatus.STANDBY,
    models.RosterAssignmentStatus.TRAVEL,
    models.RosterAssignmentStatus.OTHER,
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _interval_overlaps(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return _aware(left_start) < _aware(right_end) and _aware(left_end) > _aware(right_start)


def _assignment_minutes(row: models.RosterAssignment) -> int:
    if row.planned_minutes is not None:
        return int(row.planned_minutes)
    return workforce_calculations.duration_minutes(_aware(row.starts_at), _aware(row.ends_at))


def coverage_recommendations(
    db: Session,
    *,
    version: models.RosterVersion,
    candidate_limit: int = 5,
) -> schemas.RosterCoverageRecommendationResponse:
    """Recommend auditable substitutes for duty displaced by source commitments.

    Approved leave, scheduled Training and Quality assignments remain owned by
    their source modules. This service only recommends eligible people for the
    affected draft duty; it never mutates the roster while reading suggestions.
    """
    roster_rows = list_assignments(db, amo_id=version.amo_id, version_id=version.id)
    busy_rows = [row for row in roster_rows if row.status in _BUSY_ASSIGNMENT_STATUSES]
    aircraft_counts = {
        assignment_id: int(count)
        for assignment_id, count in db.query(
            RosterAircraftAllocation.roster_assignment_id,
            func.count(RosterAircraftAllocation.id),
        ).filter(
            RosterAircraftAllocation.amo_id == version.amo_id,
            RosterAircraftAllocation.roster_assignment_id.in_([row.id for row in busy_rows] or ["__none__"]),
        ).group_by(RosterAircraftAllocation.roster_assignment_id).all()
    }
    source_commitments = commitments.list_commitments(
        db,
        amo_id=version.amo_id,
        from_date=version.period.starts_on,
        to_date=version.period.ends_on,
    ).items
    commitments_by_user: dict[str, list[commitments.RosterCommitmentRead]] = {}
    for item in source_commitments:
        if item.blocking:
            commitments_by_user.setdefault(item.user_id, []).append(item)

    people = db.query(account_models.User).filter(
        account_models.User.amo_id == version.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name.asc(), account_models.User.staff_code.asc(), account_models.User.id.asc()).all()
    person_ids = [row.id for row in people]
    authorisations_by_user: dict[str, list[account_models.UserAuthorisation]] = {}
    if person_ids:
        for authorisation in db.query(account_models.UserAuthorisation).filter(
            account_models.UserAuthorisation.user_id.in_(person_ids),
        ).all():
            authorisations_by_user.setdefault(authorisation.user_id, []).append(authorisation)

    recommendations: list[schemas.RosterCoverageRecommendationRead] = []
    certifying_roles = {
        account_models.AccountRole.CERTIFYING_ENGINEER,
        account_models.AccountRole.CERTIFYING_TECHNICIAN,
    }
    for assignment in busy_rows:
        conflicts = [
            item for item in commitments_by_user.get(assignment.user_id, [])
            if _interval_overlaps(assignment.starts_at, assignment.ends_at, item.starts_at, item.ends_at)
        ]
        if not conflicts:
            continue
        conflict = sorted(conflicts, key=lambda item: (item.starts_at, item.id))[0]
        duty_date = _aware(assignment.starts_at).date()
        duty_end_date = (_aware(assignment.ends_at) - timedelta(microseconds=1)).date()
        absent_user = assignment.user
        requires_certifying = any(
            token in (assignment.role_label or "").lower()
            for token in ("certif", "inspect", "release")
        ) or getattr(absent_user, "role", None) in certifying_roles
        scored: list[schemas.RosterCoverageCandidateRead] = []

        for person in people:
            if person.id == assignment.user_id:
                continue
            start_contract = workforce_services.active_contract_for_user(
                db,
                amo_id=version.amo_id,
                user_id=person.id,
                on_date=duty_date,
            )
            end_contract = workforce_services.active_contract_for_user(
                db,
                amo_id=version.amo_id,
                user_id=person.id,
                on_date=duty_end_date,
            )
            if not start_contract or not end_contract:
                continue
            if assignment.status == models.RosterAssignmentStatus.STANDBY and not start_contract.standby_eligible:
                continue
            shift_kind = getattr(getattr(assignment, "shift_template", None), "kind", None)
            if shift_kind == models.ShiftTemplateKind.NIGHT and not start_contract.night_shift_eligible:
                continue
            if any(
                _interval_overlaps(assignment.starts_at, assignment.ends_at, item.starts_at, item.ends_at)
                for item in commitments_by_user.get(person.id, [])
            ):
                continue
            if any(
                row.user_id == person.id
                and row.id != assignment.id
                and _interval_overlaps(assignment.starts_at, assignment.ends_at, row.starts_at, row.ends_at)
                for row in busy_rows
            ):
                continue

            valid_authorisations = [
                row for row in authorisations_by_user.get(person.id, [])
                if row.is_currently_valid(duty_date)
            ]
            if requires_certifying and person.role not in certifying_roles and not valid_authorisations:
                continue
            department_match = bool(assignment.department_id and person.department_id == assignment.department_id)
            base_match = bool(
                assignment.base_station_id
                and getattr(start_contract, "primary_base_station_id", None) == assignment.base_station_id
            )
            role_match = bool(absent_user and person.role == absent_user.role)
            window_start = _aware(assignment.starts_at) - timedelta(days=7)
            window_end = _aware(assignment.ends_at) + timedelta(days=7)
            workload_minutes = sum(
                _assignment_minutes(row)
                for row in busy_rows
                if row.user_id == person.id
                and _aware(row.starts_at) < window_end
                and _aware(row.ends_at) > window_start
            )
            score = 20
            reasons: list[str] = []
            if department_match:
                score += 30
                reasons.append("same department")
            if base_match:
                score += 30
                reasons.append("same effective base")
            if role_match:
                score += 20
                reasons.append("same roster role")
            if valid_authorisations:
                score += min(len(valid_authorisations) * 5, 15)
                reasons.append(f"{len(valid_authorisations)} current authorisation{'s' if len(valid_authorisations) != 1 else ''}")
            load_bonus = max(15 - int(workload_minutes / 480) * 3, 0)
            score += load_bonus
            if load_bonus >= 9:
                reasons.append("lighter 14-day roster load")
            if not reasons:
                reasons.append("available and contract eligible")
            scored.append(schemas.RosterCoverageCandidateRead(
                user_id=person.id,
                full_name=person.full_name,
                staff_code=person.staff_code,
                score=score,
                workload_minutes=workload_minutes,
                department_match=department_match,
                base_match=base_match,
                role_match=role_match,
                active_authorisation_count=len(valid_authorisations),
                reasons=reasons,
            ))

        scored.sort(key=lambda row: (-row.score, row.workload_minutes, row.full_name.lower(), row.user_id))
        recommendations.append(schemas.RosterCoverageRecommendationRead(
            assignment_id=assignment.id,
            assignment_state_revision=assignment.state_revision,
            absent_user_id=assignment.user_id,
            absent_user_full_name=getattr(absent_user, "full_name", None) or assignment.user_id,
            shift_code=getattr(getattr(assignment, "shift_template", None), "code", None),
            shift_label=getattr(getattr(assignment, "shift_template", None), "label", None),
            starts_at=assignment.starts_at,
            ends_at=assignment.ends_at,
            commitment_id=conflict.id,
            commitment_kind=conflict.kind,
            commitment_title=conflict.title,
            commitment_source_module=conflict.source_module,
            linked_task_count=len(assignment.task_links or []),
            aircraft_allocation_count=aircraft_counts.get(assignment.id, 0),
            candidates=scored[:max(1, min(candidate_limit, 10))],
        ))

    recommendations.sort(key=lambda row: (row.starts_at, row.absent_user_full_name.lower(), row.assignment_id))
    return schemas.RosterCoverageRecommendationResponse(
        version_id=version.id,
        generated_at=datetime.now(timezone.utc),
        conflict_count=len(recommendations),
        items=recommendations,
    )


def apply_coverage_recommendation(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
    payload: schemas.RosterCoverageRecommendationApplyRequest,
) -> schemas.RosterCoverageRecommendationApplyResult:
    common.ensure_draft(version)
    source_reference_id = f"COVERAGE:{payload.assignment_id}:{common.canonical_hash(payload.idempotency_key)[:32]}"
    replay = db.query(models.RosterAssignment).filter(
        models.RosterAssignment.version_id == version.id,
        models.RosterAssignment.source_reference_id == source_reference_id,
        models.RosterAssignment.deleted_at.is_(None),
    ).first()
    if replay:
        return schemas.RosterCoverageRecommendationApplyResult(
            removed_assignment_id=payload.assignment_id,
            replacement_assignment=common.serialize_assignment(replay),
        )

    original = get_assignment(
        db,
        amo_id=version.amo_id,
        assignment_id=payload.assignment_id,
        include_deleted=False,
        lock=True,
    )
    if not original or original.version_id != version.id:
        raise ValueError("The affected roster assignment was not found in this draft")
    common.check_assignment_revision(original, payload.expected_assignment_revision)
    recommendation = next(
        (item for item in coverage_recommendations(db, version=version).items if item.assignment_id == original.id),
        None,
    )
    if not recommendation:
        raise ValueError("This duty no longer conflicts with approved leave, Training or Quality work")
    candidate = next((item for item in recommendation.candidates if item.user_id == payload.replacement_user_id), None)
    if not candidate:
        raise ValueError("The selected replacement is no longer eligible or available; refresh recommendations")

    replacement = create_assignment(
        db,
        version=version,
        actor_user_id=actor_user_id,
        payload=schemas.RosterAssignmentCreate(
            user_id=candidate.user_id,
            starts_at=original.starts_at,
            ends_at=original.ends_at,
            department_id=None,
            base_station_id=None,
            shift_template_id=original.shift_template_id,
            status=original.status,
            source=models.RosterAssignmentSource.MANUAL,
            source_reference_id=source_reference_id,
            planned_minutes=original.planned_minutes,
            role_label=original.role_label,
            team_code=original.team_code,
            location_label=original.location_label,
            task_note=original.task_note,
            change_reason=payload.reason.strip(),
        ),
    )
    for link in list(original.task_links or []):
        task_assignment = link.task_assignment
        if not task_assignment:
            raise ValueError("A linked maintenance task assignment could not be loaded for rotation")
        if task_assignment.status == work_models.TaskAssignmentStatusEnum.COMPLETED:
            raise ValueError("Completed maintenance work cannot be reassigned by roster rotation")
        existing_task_assignment = db.query(work_models.TaskAssignment).filter(
            work_models.TaskAssignment.amo_id == original.amo_id,
            work_models.TaskAssignment.task_id == task_assignment.task_id,
            work_models.TaskAssignment.user_id == candidate.user_id,
            work_models.TaskAssignment.role_on_task == task_assignment.role_on_task,
            work_models.TaskAssignment.id != task_assignment.id,
        ).first()
        before_task_user_id = task_assignment.user_id
        if existing_task_assignment:
            link.task_assignment_id = existing_task_assignment.id
            task_assignment.status = work_models.TaskAssignmentStatusEnum.REJECTED
            db.add(task_assignment)
        else:
            task_assignment.user_id = candidate.user_id
            task_assignment.status = work_models.TaskAssignmentStatusEnum.ASSIGNED
            db.add(task_assignment)
        link.roster_assignment_id = replacement.id
        db.add(link)
        common.audit(
            db,
            amo_id=original.amo_id,
            actor_user_id=actor_user_id,
            entity_type="RosterTaskAssignmentLink",
            entity_id=link.id,
            action="coverage_rotate",
            before={"roster_assignment_id": original.id, "task_user_id": before_task_user_id},
            after={"roster_assignment_id": replacement.id, "task_user_id": candidate.user_id},
            metadata={"reason": payload.reason.strip()},
        )
    for allocation in db.query(RosterAircraftAllocation).filter(
        RosterAircraftAllocation.amo_id == original.amo_id,
        RosterAircraftAllocation.roster_assignment_id == original.id,
    ).all():
        allocation.roster_assignment_id = replacement.id
        db.add(allocation)
        common.audit(
            db,
            amo_id=original.amo_id,
            actor_user_id=actor_user_id,
            entity_type="RosterAircraftAllocation",
            entity_id=allocation.id,
            action="coverage_rotate",
            before={"roster_assignment_id": original.id},
            after={"roster_assignment_id": replacement.id},
            metadata={"reason": payload.reason.strip()},
        )
    db.flush()
    delete_assignment(
        db,
        row=original,
        actor_user_id=actor_user_id,
        payload=schemas.RosterAssignmentDeleteRequest(
            reason=payload.reason.strip(),
            expected_state_revision=payload.expected_assignment_revision,
        ),
    )
    db.flush()
    db.expire(replacement, ["task_links"])
    return schemas.RosterCoverageRecommendationApplyResult(
        removed_assignment_id=original.id,
        replacement_assignment=common.serialize_assignment(replacement),
    )


def get_shift_template(db: Session, *, amo_id: str, template_id: str):
    from . import models

    return db.query(models.ShiftTemplate).filter(
        models.ShiftTemplate.amo_id == amo_id,
        models.ShiftTemplate.id == template_id,
    ).first()


def get_rule(db: Session, *, amo_id: str, rule_id: str):
    from . import models

    return db.query(models.RosterRule).filter(models.RosterRule.amo_id == amo_id, models.RosterRule.id == rule_id).first()


def get_demand_requirement(db: Session, *, amo_id: str, demand_id: str):
    from . import models

    return db.query(models.RosterDemandRequirement).filter(
        models.RosterDemandRequirement.amo_id == amo_id,
        models.RosterDemandRequirement.id == demand_id,
    ).first()


def get_finding(db: Session, *, amo_id: str, finding_id: str):
    from . import models

    return db.query(models.RosterValidationFinding).filter(
        models.RosterValidationFinding.amo_id == amo_id,
        models.RosterValidationFinding.id == finding_id,
    ).first()


def get_exception(db: Session, *, amo_id: str, exception_id: str):
    from . import models

    return db.query(models.RosterRuleException).filter(
        models.RosterRuleException.amo_id == amo_id,
        models.RosterRuleException.id == exception_id,
    ).first()


def published_version_for_date(db: Session, *, amo_id: str, on_date: date):
    from . import models

    return db.query(models.RosterVersion).join(
        models.RosterPeriod,
        models.RosterVersion.period_id == models.RosterPeriod.id,
    ).filter(
        models.RosterVersion.amo_id == amo_id,
        models.RosterVersion.status == models.RosterVersionStatus.PUBLISHED,
        models.RosterPeriod.starts_on <= on_date,
        models.RosterPeriod.ends_on >= on_date,
    ).order_by(models.RosterVersion.published_at.desc(), models.RosterVersion.version_no.desc()).first()


list_rule_sets = governance.list_rule_sets
create_rule_set = governance.create_rule_set
update_rule_set = governance.update_rule_set
list_approval_authorities = governance.list_authorities
create_approval_authority = governance.create_authority
update_approval_authority = governance.update_authority
approval_matrix = governance.approval_matrix
request_roster_changes = governance.request_changes


__all__ = [name for name in globals() if not name.startswith("_")]
