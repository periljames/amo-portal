"""Controlled manual-revision training impact, without a duplicate Training engine.

Quality can explicitly link immutable published DMS revisions to existing
TrainingRequirement rows or create USER-scoped Training requirements. Training
owns course validation, completion and competence. Document Control owns
publication, distribution and acknowledgements. Nothing here auto-publishes,
approves a training record, or treats course completion as revision sign-off.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.training import models as training_models
from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _log_qms_activity
from .tenant_security import (
    TenantContext, assert_quality_permission, require_quality_permission,
    set_postgres_tenant_context,
)

router = APIRouter(prefix="/manual-impact", tags=["Controlled manual training impact"])


class TrainingImpactAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str = Field(min_length=1, max_length=36)
    target_user_ids: list[str] = Field(min_length=1, max_length=50)
    required_by_date: date
    mandatory: bool = True
    blocking: bool = False
    decision_basis: str = Field(min_length=12, max_length=4000)

    @model_validator(mode="after")
    def distinct_targets(self):
        if len(self.target_user_ids) != len(set(self.target_user_ids)):
            raise ValueError("Each target employee can appear only once.")
        return self


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _revision(db: Session, ctx: TenantContext, manual_id: str, revision_id: str) -> tuple[manual_models.Manual, manual_models.ManualRevision]:
    manual = (
        db.query(manual_models.Manual)
        .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
        .filter(manual_models.Tenant.amo_id == ctx.amo_id, manual_models.Manual.id == manual_id)
        .first()
    )
    if not manual:
        raise HTTPException(404, "Controlled document is not available in this organisation.")
    revision = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.manual_id == manual.id,
        manual_models.ManualRevision.id == revision_id,
    ).first()
    if not revision:
        raise HTTPException(404, "Revision was not found for this controlled manual.")
    return manual, revision


def _is_published_current(manual: manual_models.Manual, revision: manual_models.ManualRevision) -> bool:
    state = getattr(revision.status_enum, "value", revision.status_enum)
    return state == "PUBLISHED" and str(manual.current_published_rev_id or "") == str(revision.id)


def _linked_requirements(db: Session, ctx: TenantContext, manual_id: str, revision_id: str) -> list[dict[str, Any]]:
    rows = db.execute(text(
        "SELECT link.id, link.immutable_source_sha256, link.rationale, link.linked_at, "
        "link.linked_by_user_id, req.id AS requirement_id, req.course_id, req.user_id, "
        "req.required_by_date, req.is_active, req.is_mandatory, req.blocking "
        "FROM manual_revision_training_links link "
        "JOIN training_requirements req ON req.id=link.training_requirement_id AND req.amo_id=link.amo_id "
        "WHERE link.amo_id=:amo_id AND link.manual_id=:manual_id AND link.revision_id=:revision_id "
        "ORDER BY link.linked_at DESC LIMIT 251"
    ), {"amo_id": ctx.amo_id, "manual_id": manual_id, "revision_id": revision_id}).mappings().all()
    if len(rows) > 250:
        raise HTTPException(409, "Training impact exceeds the verified limit; use paginated review.")
    return [dict(row) for row in rows]


@router.get("/catalog")
def course_and_people_catalog(
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    assert_quality_permission(db, ctx, "qms.document.view")
    courses = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.amo_id == ctx.amo_id,
                training_models.TrainingCourse.is_active.is_(True))
        .order_by(training_models.TrainingCourse.course_id).limit(100).all()
    )
    people = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name).limit(200).all()
    return {"courses": [{"id": c.id, "code": c.course_id, "title": c.course_name} for c in courses],
            "people": [{"id": p.id, "name": p.full_name} for p in people]}


@router.get("/manuals/{manual_id}/revisions/{revision_id}")
def revision_training_impact(
    manual_id: str, revision_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    assert_quality_permission(db, ctx, "qms.document.view")
    manual, revision = _revision(db, ctx, manual_id, revision_id)
    links = _linked_requirements(db, ctx, manual_id, revision_id)
    states = {}
    for item in links:
        user_id, course_id = item["user_id"], item["course_id"]
        # Course record is NOT evidence of reading or acknowledging this revision.
        record = db.query(training_models.TrainingRecord).filter(
            training_models.TrainingRecord.amo_id == ctx.amo_id,
            training_models.TrainingRecord.user_id == user_id,
            training_models.TrainingRecord.course_id == course_id,
            training_models.TrainingRecord.record_status == "ACTIVE",
        ).order_by(training_models.TrainingRecord.completion_date.desc()).first()
        if record is None:
            summary = {"course_record_id": None, "course_record_state": "NO_ACTIVE_RECORD"}
        else:
            verified = getattr(record.verification_status, "value", record.verification_status) == "VERIFIED"
            current = record.valid_until is None or record.valid_until >= date.today()
            summary = {"course_record_id": record.id, "course_record_state":
                       "VERIFIED_COURSE_RECORD" if verified and current else "NOT_CURRENTLY_VERIFIED"}
        states[item["requirement_id"]] = summary
    acknowledgements = db.query(manual_models.Acknowledgement).filter(
        manual_models.Acknowledgement.revision_id == revision_id,
    ).limit(251).all()
    if len(acknowledgements) > 250:
        raise HTTPException(409, "Acknowledgement population exceeds the bounded view.")
    acknowledged = sum(1 for row in acknowledgements if row.acknowledged_at is not None)
    return {
        "manual": {"id": manual.id, "code": manual.code, "title": manual.title},
        "revision": {"id": revision.id, "number": revision.rev_number,
                     "published_current": _is_published_current(manual, revision),
                     "status": getattr(revision.status_enum, "value", revision.status_enum),
                     "immutable_source_sha256": revision.source_sha256,
                     "immutable_locked": bool(revision.immutable_locked)},
        "requirements": [{**row, "course_completion": states.get(row["requirement_id"])}
                         for row in links],
        "acknowledgement": {
            "assigned_count": len(acknowledgements), "acknowledged_count": acknowledged,
            "pending_count": len(acknowledgements) - acknowledged,
            "authority": "DOCUMENT_CONTROL",
        },
        "training_authority": "TRAINING",
        "warning": "A verified training course alone does not constitute manual revision acknowledgement.",
    }


@router.post("/manuals/{manual_id}/revisions/{revision_id}/assign", status_code=201)
def assign_revision_training(
    manual_id: str, revision_id: str, body: TrainingImpactAssignment, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    assert_quality_permission(db, ctx, "qms.document.view")
    manual, revision = _revision(db, ctx, manual_id, revision_id)
    if not _is_published_current(manual, revision) or not revision.immutable_locked:
        raise HTTPException(409, "Only the immutable current published revision may trigger training requirements.")
    if not revision.source_sha256:
        raise HTTPException(409, "Immutable source identity is required before linking training.")
    if body.required_by_date < date.today():
        raise HTTPException(422, "New training assignments must have a due date today or later.")
    course = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == ctx.amo_id,
        training_models.TrainingCourse.id == body.course_id,
        training_models.TrainingCourse.is_active.is_(True),
    ).with_for_update().first()
    if not course:
        raise HTTPException(422, "The selected active Training course does not belong to this organisation.")
    targets = db.query(account_models.User.id).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id.in_(body.target_user_ids),
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    if {row[0] for row in targets} != set(body.target_user_ids):
        raise HTTPException(422, "Training targets must all be active people belonging to this organisation.")
    saved: list[dict[str, Any]] = []
    for user_id in body.target_user_ids:
        requirements = db.query(training_models.TrainingRequirement).filter(
            training_models.TrainingRequirement.amo_id == ctx.amo_id,
            training_models.TrainingRequirement.user_id == user_id,
            training_models.TrainingRequirement.course_id == body.course_id,
            training_models.TrainingRequirement.scope == training_models.TrainingRequirementScope.USER,
            training_models.TrainingRequirement.is_active.is_(True),
        ).order_by(training_models.TrainingRequirement.created_at.desc()).limit(2).all()
        if len(requirements) > 1:
            raise HTTPException(409, "Duplicate active USER-scoped requirements already exist in Training. Reconcile there first.")
        if requirements:
            req = requirements[0]
            # An existing Training requirement remains authoritative and is
            # never silently modified by Document Control impact planning.
            if body.blocking and not req.blocking:
                raise HTTPException(409, "An existing nonblocking Training requirement cannot become blocking by DMS linkage. Change it in Training.")
        else:
            req = training_models.TrainingRequirement(
                amo_id=ctx.amo_id, course_id=body.course_id,
                scope=training_models.TrainingRequirementScope.USER, user_id=user_id,
                is_mandatory=body.mandatory, is_active=True, blocking=body.blocking,
                required_by_date=body.required_by_date,
                effective_from=revision.effective_date,
                manual_reference=manual.code + " Rev " + revision.rev_number,
                source_type="MANUAL_REVISION", source_id=revision.id,
                created_by_user_id=ctx.user_id,
            )
            db.add(req)
            db.flush()
        link_id = str(uuid4())
        linked = db.execute(text(
            "INSERT INTO manual_revision_training_links "
            "(id,amo_id,manual_id,revision_id,training_requirement_id,"
            "immutable_source_sha256,rationale,linked_by_user_id,linked_at) "
            "VALUES (:id,:amo_id,:manual_id,:revision_id,:requirement_id,:sha,:rationale,:actor,NOW()) "
            "ON CONFLICT (amo_id,revision_id,training_requirement_id) DO NOTHING RETURNING id"
        ), {"id": link_id, "amo_id": ctx.amo_id, "manual_id": manual.id,
            "revision_id": revision.id, "requirement_id": req.id,
            "sha": revision.source_sha256, "rationale": body.decision_basis,
            "actor": ctx.user_id}).scalar()
        saved.append({"training_requirement_id": req.id, "user_id": user_id,
                      "link_id": linked, "existing_link": linked is None})
    _log_qms_activity(
        db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
        action="manual_revision_training_assignment", module="training-competence",
        entity_type="manual_revisions", entity_id=revision.id,
        new_value={"source_sha256": revision.source_sha256, "course_id": course.id,
                   "target_user_ids": body.target_user_ids, "decision_basis": body.decision_basis,
                   "assignments": saved, "blocking": body.blocking}, request=request,
    )
    db.commit()
    return {"manual_id": manual.id, "revision_id": revision.id,
            "source_sha256": revision.source_sha256, "assignments": saved,
            "message": "Training requirements were linked; completion and document acknowledgements remain independent."}
