"""Cross-cutting integrity controls for corporate position assignments.

The reporting-line and corporate-structure routers both create and change
``PositionAssignment`` rows. This module installs one SQLAlchemy flush guard so
all write paths receive the same overlap, primary-position and headcount rules.
The guard locks the affected user and position rows before checking, which
serialises concurrent writes on PostgreSQL and prevents two requests from both
passing an application-only capacity check.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import event, or_
from sqlalchemy.orm import Session

from . import corporate_structure_models as org_models
from . import models

ACTIVE_STATUSES = {"ACTIVE", "ACTING", "APPROVED"}
_LISTENER_FLAG = "_corporate_assignment_integrity_listener"


def periods_overlap(
    first_start: date,
    first_end: Optional[date],
    second_start: date,
    second_end: Optional[date],
) -> bool:
    """Return whether two inclusive effective-date ranges overlap."""
    return (first_end is None or first_end >= second_start) and (
        second_end is None or second_end >= first_start
    )


def _is_active_candidate(row: org_models.PositionAssignment) -> bool:
    return str(row.status or "").upper() in ACTIVE_STATUSES


def _candidate_rows(session: Session) -> list[org_models.PositionAssignment]:
    rows: list[org_models.PositionAssignment] = []
    for row in list(session.new) + list(session.dirty):
        if not isinstance(row, org_models.PositionAssignment):
            continue
        if row in session.deleted:
            continue
        rows.append(row)
    return rows


def _lock_subjects(session: Session, row: org_models.PositionAssignment) -> None:
    # PostgreSQL honours FOR UPDATE. SQLite safely treats it as a normal SELECT,
    # which keeps unit tests portable while production receives serialisation.
    session.query(models.User.id).filter(models.User.id == row.user_id).with_for_update().first()
    session.query(org_models.OrganizationPosition.id).filter(
        org_models.OrganizationPosition.id == row.position_id,
    ).with_for_update().first()


def _overlap_filter(row: org_models.PositionAssignment):
    return (
        org_models.PositionAssignment.effective_from
        <= (row.effective_to if row.effective_to is not None else date.max),
        or_(
            org_models.PositionAssignment.effective_to.is_(None),
            org_models.PositionAssignment.effective_to >= row.effective_from,
        ),
    )


def _candidate_overlap_count(
    candidates: Iterable[org_models.PositionAssignment],
    row: org_models.PositionAssignment,
    *,
    same_user_primary: bool = False,
    same_position: bool = False,
) -> int:
    count = 0
    for other in candidates:
        if other is row or not _is_active_candidate(other):
            continue
        if same_user_primary and not (
            bool(row.is_primary)
            and bool(other.is_primary)
            and str(other.user_id) == str(row.user_id)
        ):
            continue
        if same_position and str(other.position_id) != str(row.position_id):
            continue
        if periods_overlap(
            row.effective_from,
            row.effective_to,
            other.effective_from,
            other.effective_to,
        ):
            count += 1
    return count


def validate_assignment_integrity(session: Session, *_args) -> None:
    candidates = _candidate_rows(session)
    if not candidates:
        return
    candidate_ids = [str(row.id) for row in candidates if row.id]

    with session.no_autoflush:
        for row in candidates:
            if row.effective_to and row.effective_to < row.effective_from:
                raise HTTPException(
                    status_code=422,
                    detail="Assignment end date cannot be before its start date.",
                )
            if not _is_active_candidate(row):
                continue

            _lock_subjects(session, row)

            if bool(row.is_primary):
                primary_query = session.query(org_models.PositionAssignment.id).filter(
                    org_models.PositionAssignment.amo_id == row.amo_id,
                    org_models.PositionAssignment.user_id == row.user_id,
                    org_models.PositionAssignment.is_primary.is_(True),
                    org_models.PositionAssignment.status.in_(ACTIVE_STATUSES),
                    *_overlap_filter(row),
                )
                if candidate_ids:
                    primary_query = primary_query.filter(
                        ~org_models.PositionAssignment.id.in_(candidate_ids),
                    )
                if primary_query.first() or _candidate_overlap_count(
                    candidates,
                    row,
                    same_user_primary=True,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "The person already has a primary position assignment "
                            "overlapping this effective period. End, transfer or revise "
                            "the existing assignment first."
                        ),
                    )

            position = session.query(org_models.OrganizationPosition).filter(
                org_models.OrganizationPosition.id == row.position_id,
                org_models.OrganizationPosition.amo_id == row.amo_id,
            ).first()
            if not position:
                raise HTTPException(status_code=404, detail="Assigned position was not found.")

            occupied_query = session.query(org_models.PositionAssignment.id).filter(
                org_models.PositionAssignment.amo_id == row.amo_id,
                org_models.PositionAssignment.position_id == row.position_id,
                org_models.PositionAssignment.status.in_(ACTIVE_STATUSES),
                *_overlap_filter(row),
            )
            if candidate_ids:
                occupied_query = occupied_query.filter(
                    ~org_models.PositionAssignment.id.in_(candidate_ids),
                )
            occupied = occupied_query.count() + _candidate_overlap_count(
                candidates,
                row,
                same_position=True,
            )
            if occupied >= int(position.headcount_limit or 1):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The approved headcount for this position is filled during "
                        "the selected effective period."
                    ),
                )


def install_assignment_integrity_listener() -> None:
    if getattr(Session, _LISTENER_FLAG, False):
        return
    event.listen(Session, "before_flush", validate_assignment_integrity)
    setattr(Session, _LISTENER_FLAG, True)


install_assignment_integrity_listener()
