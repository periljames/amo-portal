"""Preview and execute explicit, effective-dated work-pattern batch changes."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, lazyload

from ..accounts import models as account_models
from ..audit import services as audit_services
from . import bulk_models, bulk_schemas, hr_selection_integrity, models, permissions, services

MAX_BULK_RECORDS = 10_000
QUERY_CHUNK_SIZE = 500


def _chunks(values: list[str], size: int = QUERY_CHUNK_SIZE) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _assignment_snapshot(row: models.EmployeeWorkPatternAssignment) -> dict[str, Any]:
    return {
        "user_id": str(row.user_id),
        "work_pattern_id": str(row.work_pattern_id),
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
    }


def _overlapping_assignments(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
    effective_from: date,
    effective_to: date | None,
) -> dict[str, list[models.EmployeeWorkPatternAssignment]]:
    result: dict[str, list[models.EmployeeWorkPatternAssignment]] = defaultdict(list)
    end = effective_to or date.max
    for chunk in _chunks(user_ids):
        rows = db.query(models.EmployeeWorkPatternAssignment).options(
            joinedload(models.EmployeeWorkPatternAssignment.work_pattern),
        ).filter(
            models.EmployeeWorkPatternAssignment.amo_id == amo_id,
            models.EmployeeWorkPatternAssignment.user_id.in_(chunk),
            models.EmployeeWorkPatternAssignment.effective_from <= end,
            or_(
                models.EmployeeWorkPatternAssignment.effective_to.is_(None),
                models.EmployeeWorkPatternAssignment.effective_to >= effective_from,
            ),
        ).order_by(
            models.EmployeeWorkPatternAssignment.user_id.asc(),
            models.EmployeeWorkPatternAssignment.effective_from.asc(),
        ).all()
        for row in rows:
            result[str(row.user_id)].append(row)
    return result


def _same_pattern_covers_window(
    rows: list[models.EmployeeWorkPatternAssignment],
    *,
    options: bulk_schemas.WorkPatternBatchOptions,
) -> bool:
    target_end = options.effective_to or date.max
    return any(
        str(row.work_pattern_id) == options.work_pattern_id
        and row.cycle_anchor_date == options.cycle_anchor_date
        and row.effective_from <= options.effective_from
        and (row.effective_to or date.max) >= target_end
        for row in rows
    )


def classify_work_pattern_batch(
    db: Session,
    *,
    amo_id: str,
    actor: account_models.User,
    user_ids: list[str],
    options: bulk_schemas.WorkPatternBatchOptions,
) -> tuple[models.WorkPattern, list[bulk_schemas.WorkPatternPreviewRow]]:
    pattern = services.get_pattern(db, amo_id=amo_id, pattern_id=options.work_pattern_id)
    if pattern is None or not pattern.is_active:
        raise ValueError("Active work pattern not found")

    users: list[account_models.User] = []
    for chunk in _chunks(user_ids):
        users.extend(
            db.query(account_models.User).options(joinedload(account_models.User.department)).filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id.in_(chunk),
            ).all()
        )
    users.sort(key=lambda row: ((row.full_name or "").lower(), str(row.id)))
    overlap_by_user = _overlapping_assignments(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
        effective_from=options.effective_from,
        effective_to=options.effective_to,
    )

    rows: list[bulk_schemas.WorkPatternPreviewRow] = []
    for user in users:
        reasons: list[str] = []
        user_id = str(user.id)
        overlaps = overlap_by_user.get(user_id, [])
        current = next(
            (row for row in overlaps if row.effective_from <= options.effective_from <= (row.effective_to or date.max)),
            overlaps[0] if overlaps else None,
        )
        if not user.is_active or user.is_system_account:
            reasons.append("ACCOUNT_INELIGIBLE")
        if not permissions.has_permission(
            db,
            user=actor,
            permission=permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
            department_id=user.department_id,
        ):
            reasons.append("OUTSIDE_PERMISSION_SCOPE")
        try:
            services._validate_pattern_user_shift_scope(pattern, user=user)
        except ValueError as exc:
            reasons.append(str(exc))

        if reasons:
            action = "BLOCKED"
        elif _same_pattern_covers_window(overlaps, options=options):
            action = "UNCHANGED"
        elif overlaps and options.conflict_strategy == "SKIP_ASSIGNED":
            action = "SKIP"
        elif overlaps:
            action = "REPLACE"
        else:
            action = "ASSIGN"
        rows.append(
            bulk_schemas.WorkPatternPreviewRow(
                user_id=user_id,
                staff_code=user.staff_code,
                full_name=user.full_name or user.email or user_id,
                department_name=getattr(user.department, "name", None),
                current_pattern_code=getattr(getattr(current, "work_pattern", None), "code", None),
                current_pattern_name=getattr(getattr(current, "work_pattern", None), "name", None),
                target_pattern_code=pattern.code,
                target_pattern_name=pattern.name,
                action=action,
                eligible=action in {"ASSIGN", "REPLACE"},
                reasons=reasons,
            )
        )
    return pattern, rows


def preview_work_pattern_batch(
    db: Session,
    *,
    amo_id: str,
    actor: account_models.User,
    payload: bulk_schemas.WorkPatternBatchPreviewRequest,
) -> bulk_schemas.WorkPatternBatchPreview:
    user_ids, selection_token = hr_selection_integrity.resolve_with_token(
        db, amo_id=amo_id, selection=payload.selection
    )
    if not user_ids:
        raise ValueError("At least one person must be selected")
    if len(user_ids) > MAX_BULK_RECORDS:
        raise ValueError(f"Bulk operations are limited to {MAX_BULK_RECORDS:,} records")
    pattern, rows = classify_work_pattern_batch(
        db,
        amo_id=amo_id,
        actor=actor,
        user_ids=user_ids,
        options=payload.options,
    )
    counts = Counter(row.action for row in rows)
    visible_rows = rows[: payload.preview_limit]
    return bulk_schemas.WorkPatternBatchPreview(
        selection_token=selection_token,
        matched_count=len(user_ids),
        eligible_count=counts["ASSIGN"] + counts["REPLACE"],
        blocked_count=counts["BLOCKED"],
        assign_count=counts["ASSIGN"],
        replace_count=counts["REPLACE"],
        unchanged_count=counts["UNCHANGED"],
        skipped_count=counts["SKIP"],
        target_pattern_id=str(pattern.id),
        target_pattern_code=pattern.code,
        target_pattern_name=pattern.name,
        rows=visible_rows,
        rows_truncated=len(rows) > len(visible_rows),
    )


def _log_assignment_change(
    db: Session,
    *,
    operation: bulk_models.WorkforceBulkOperation,
    assignment_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    audit_services.log_event(
        db,
        amo_id=operation.amo_id,
        actor_user_id=operation.actor_user_id,
        entity_type="EmployeeWorkPatternAssignment",
        entity_id=str(assignment_id),
        action=action,
        correlation_id=str(operation.id),
        before=before,
        after=after,
        metadata={"module": "workforce", "bulk_operation_id": str(operation.id)},
    )


def _replace_assignment_window(
    db: Session,
    *,
    operation: bulk_models.WorkforceBulkOperation,
    user: account_models.User,
    options: bulk_schemas.WorkPatternBatchOptions,
) -> tuple[models.EmployeeWorkPatternAssignment, int, bool]:
    target_end = options.effective_to or date.max
    overlaps = db.query(models.EmployeeWorkPatternAssignment).options(
        lazyload(models.EmployeeWorkPatternAssignment.user),
        lazyload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == operation.amo_id,
        models.EmployeeWorkPatternAssignment.user_id == user.id,
        models.EmployeeWorkPatternAssignment.effective_from <= target_end,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= options.effective_from,
        ),
    ).order_by(models.EmployeeWorkPatternAssignment.effective_from.asc()).with_for_update(
        of=models.EmployeeWorkPatternAssignment
    ).all()

    if _same_pattern_covers_window(overlaps, options=options):
        return next(row for row in overlaps if str(row.work_pattern_id) == options.work_pattern_id), 0, True
    if overlaps and options.conflict_strategy == "SKIP_ASSIGNED":
        raise LookupError("Existing work-pattern assignment retained")

    replaced = 0
    for row in overlaps:
        replaced += 1
        before = _assignment_snapshot(row)
        keeps_left = row.effective_from < options.effective_from
        keeps_right = options.effective_to is not None and (row.effective_to is None or row.effective_to > options.effective_to)
        if keeps_left and keeps_right:
            suffix = models.EmployeeWorkPatternAssignment(
                amo_id=row.amo_id,
                user_id=row.user_id,
                work_pattern_id=row.work_pattern_id,
                effective_from=options.effective_to + timedelta(days=1),
                effective_to=row.effective_to,
                cycle_anchor_date=row.cycle_anchor_date,
                created_by_user_id=operation.actor_user_id,
            )
            row.effective_to = options.effective_from - timedelta(days=1)
            db.add(suffix)
            db.flush()
            _log_assignment_change(
                db,
                operation=operation,
                assignment_id=str(row.id),
                action="truncate_for_batch_replacement",
                before=before,
                after=_assignment_snapshot(row),
            )
            _log_assignment_change(
                db,
                operation=operation,
                assignment_id=str(suffix.id),
                action="preserve_after_batch_replacement",
                after=_assignment_snapshot(suffix),
            )
        elif keeps_left:
            row.effective_to = options.effective_from - timedelta(days=1)
            db.flush()
            _log_assignment_change(
                db,
                operation=operation,
                assignment_id=str(row.id),
                action="truncate_for_batch_replacement",
                before=before,
                after=_assignment_snapshot(row),
            )
        elif keeps_right:
            row.effective_from = options.effective_to + timedelta(days=1)
            db.flush()
            _log_assignment_change(
                db,
                operation=operation,
                assignment_id=str(row.id),
                action="preserve_after_batch_replacement",
                before=before,
                after=_assignment_snapshot(row),
            )
        else:
            _log_assignment_change(
                db,
                operation=operation,
                assignment_id=str(row.id),
                action="replace_in_batch",
                before=before,
            )
            db.delete(row)
    db.flush()

    assignment = models.EmployeeWorkPatternAssignment(
        amo_id=operation.amo_id,
        user_id=user.id,
        work_pattern_id=options.work_pattern_id,
        effective_from=options.effective_from,
        effective_to=options.effective_to,
        cycle_anchor_date=options.cycle_anchor_date,
        created_by_user_id=operation.actor_user_id,
    )
    db.add(assignment)
    db.flush()
    _log_assignment_change(
        db,
        operation=operation,
        assignment_id=str(assignment.id),
        action="create_from_batch",
        after={**_assignment_snapshot(assignment), "reason": options.reason},
    )
    return assignment, replaced, False


def process_work_pattern_item(
    db: Session,
    *,
    operation: bulk_models.WorkforceBulkOperation,
    item: bulk_models.WorkforceBulkOperationItem,
    actor: account_models.User,
) -> tuple[str, str, str, dict[str, Any] | None]:
    user = db.query(account_models.User).options(
        lazyload(account_models.User.department),
    ).filter(
        account_models.User.amo_id == operation.amo_id,
        account_models.User.id == item.user_id,
    ).with_for_update(of=account_models.User).first()
    if user is None:
        return "FAILED", "USER_NOT_FOUND", "The selected user no longer exists in this tenant", None
    if not user.is_active or user.is_system_account:
        return "SKIPPED", "ACCOUNT_INELIGIBLE", "Inactive and system accounts cannot receive work patterns", None
    if not permissions.has_permission(
        db,
        user=actor,
        permission=permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
        department_id=user.department_id,
    ):
        return "FAILED", "OUTSIDE_PERMISSION_SCOPE", "The administrator is not authorized for this person's department", None

    options = bulk_schemas.WorkPatternBatchOptions.model_validate(item.input_json or operation.payload_json)
    pattern = services.get_pattern(db, amo_id=operation.amo_id, pattern_id=options.work_pattern_id)
    if pattern is None or not pattern.is_active:
        return "FAILED", "PATTERN_NOT_ACTIVE", "The selected work pattern is no longer active", None
    try:
        services._validate_pattern_user_shift_scope(pattern, user=user)
    except ValueError as exc:
        return "FAILED", "PATTERN_DEPARTMENT_MISMATCH", str(exc), None

    try:
        assignment, replaced, unchanged = _replace_assignment_window(
            db,
            operation=operation,
            user=user,
            options=options,
        )
    except LookupError as exc:
        return "SKIPPED", "EXISTING_ASSIGNMENT_RETAINED", str(exc), None
    if unchanged:
        return "SKIPPED", "PATTERN_UNCHANGED", "This employee already has the selected work pattern for the requested dates", {
            "assignment_id": str(assignment.id)
        }
    return "SUCCEEDED", "PATTERN_REPLACED" if replaced else "PATTERN_ASSIGNED", (
        "Work pattern changed" if replaced else "Work pattern assigned"
    ), {"assignment_id": str(assignment.id), "replaced_assignment_count": replaced}
