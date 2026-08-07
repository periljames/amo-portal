from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.aircraft_architecture.content_packs import models as content_models
from amodb.database import get_db
from amodb.security import require_roles

from . import comparison_schemas, models, overlay

router = APIRouter(prefix="/programmes", tags=["tenant maintenance programme comparison"])
PROGRAMME_READ_ROLES = ("SUPERUSER", "AMO_ADMIN", "PLANNING_ENGINEER", "QUALITY_MANAGER")


def _amo_id(user: account_models.User) -> str:
    value = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return str(value)


def _revision(db: Session, revision_id: str, user: account_models.User) -> models.TenantProgrammeRevision:
    row = db.get(models.TenantProgrammeRevision, revision_id)
    if not row or str(row.programme.amo_id) != _amo_id(user):
        raise HTTPException(status_code=404, detail="Programme revision not found")
    return row


@router.get("/aircraft-setup-defaults", response_model=dict)
def aircraft_setup_defaults(
    aircraft_type_revision_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_READ_ROLES)),
):
    """Resolve the OEM baseline and tenant AMP that aircraft induction should prefill.

    The actual induction request still carries the exact selected revision IDs so
    idempotency and engineering lineage never depend on a mutable default.
    """
    resolution = overlay.resolve_oem_baseline(db, aircraft_type_revision_id=aircraft_type_revision_id)
    candidate_oem_ids = {row["revision_id"] for row in resolution["candidates"]}
    published = (
        db.query(models.TenantProgrammeRevision)
        .join(models.TenantMaintenanceProgramme)
        .filter(
            models.TenantMaintenanceProgramme.amo_id == _amo_id(user),
            models.TenantProgrammeRevision.aircraft_type_revision_id == aircraft_type_revision_id,
            models.TenantProgrammeRevision.status == "PUBLISHED",
        )
        .all()
    )
    compatible = [row for row in published if row.base_content_pack_revision_id in candidate_oem_ids]
    programme_candidates = []
    for row in compatible:
        decisions = {"INHERIT": 0, "TIGHTEN": 0, "ADD": 0, "LEGACY": 0}
        for task in row.tasks:
            decisions[task.decision] = decisions.get(task.decision, 0) + 1
        programme_candidates.append(
            {
                "programme_id": row.programme_id,
                "programme_code": row.programme.code,
                "programme_title": row.programme.title,
                "revision_id": row.id,
                "revision_code": row.revision_code,
                "base_content_pack_revision_id": row.base_content_pack_revision_id,
                "content_hash": row.content_hash,
                "approval_reference": row.approval_reference,
                "source_currentness_at_approval": row.source_currentness_at_approval,
                "task_counts": decisions,
            }
        )

    # A published AMP bound to the uniquely derived OEM candidate is durable
    # evidence that Planning already confirmed that derived series while creating
    # the controlled AMP revision. Aircraft setup can therefore prefill it without
    # asking the same question again.
    derived_confirmed_by_published_amp = (
        resolution["state"] == "CONFIRM_DERIVED_SERIES"
        and len(resolution["candidates"]) == 1
        and len(programme_candidates) == 1
    )
    oem_ready = resolution["state"] == "RESOLVED" or derived_confirmed_by_published_amp
    if not compatible:
        state = "NO_TENANT_AMP"
    elif len(compatible) > 1:
        state = "AMBIGUOUS"
    elif oem_ready:
        state = "RESOLVED"
    else:
        state = "SERIES_CONFIRMATION_REQUIRED"

    selected = programme_candidates[0] if state == "RESOLVED" else None
    return {
        "state": state,
        "oem": resolution,
        "requires_series_confirmation": state == "SERIES_CONFIRMATION_REQUIRED",
        "programme_candidates": programme_candidates,
        "selected_programme_revision_id": selected["revision_id"] if selected else None,
        "selected_oem_baseline_revision_id": selected["base_content_pack_revision_id"] if selected else None,
        "prefill": (
            {
                "type_revision_id": aircraft_type_revision_id,
                "programme_revision_id": selected["revision_id"],
                "series": resolution["series"],
                "oem_baseline_revision_id": selected["base_content_pack_revision_id"],
            }
            if selected
            else None
        ),
    }


@router.get(
    "/revisions/{revision_id}/comparison",
    response_model=comparison_schemas.AmpComparisonPage,
)
def comparison_page(
    revision_id: str,
    search: str | None = Query(default=None, max_length=120),
    decision: str | None = Query(default=None, max_length=20),
    ata: str | None = Query(default=None, max_length=12),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_READ_ROLES)),
):
    revision = _revision(db, revision_id, user)
    query = (
        db.query(models.TenantProgrammeTask, content_models.AircraftContentPackTask)
        .outerjoin(
            content_models.AircraftContentPackTask,
            content_models.AircraftContentPackTask.id == models.TenantProgrammeTask.source_content_task_id,
        )
        .filter(models.TenantProgrammeTask.revision_id == revision.id)
    )
    if decision and decision.upper() != "ALL":
        query = query.filter(models.TenantProgrammeTask.decision == decision.upper())
    if ata:
        query = query.filter(models.TenantProgrammeTask.ata_chapter == ata)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.TenantProgrammeTask.task_code.ilike(term),
                models.TenantProgrammeTask.title.ilike(term),
                models.TenantProgrammeTask.ata_chapter.ilike(term),
            )
        )
    total = query.count()
    rows = query.order_by(models.TenantProgrammeTask.ata_chapter, models.TenantProgrammeTask.task_code).offset(offset).limit(limit).all()

    count_rows = (
        db.query(models.TenantProgrammeTask.decision, func.count(models.TenantProgrammeTask.id))
        .filter(models.TenantProgrammeTask.revision_id == revision.id)
        .group_by(models.TenantProgrammeTask.decision)
        .all()
    )
    counts = {str(key): int(value) for key, value in count_rows}
    counts["ALL"] = sum(counts.values())

    items = []
    for amp, oem in rows:
        if amp.decision == "ADD":
            state = "OPERATOR_ADDED"
        elif amp.decision == "LEGACY":
            state = "LEGACY_UNMAPPED"
        elif amp.decision == "TIGHTEN" and oem and overlay.canonical_json(amp.intervals_json or {}) != overlay.canonical_json(oem.intervals_json or {}):
            state = "MORE_RESTRICTIVE"
        else:
            state = "SAME_AS_OEM"
        items.append(
            {
                "id": amp.id,
                "source_content_task_id": amp.source_content_task_id,
                "decision": amp.decision,
                "task_code": amp.task_code,
                "title": amp.title,
                "ata_chapter": amp.ata_chapter,
                "programme_section": oem.programme_section if oem else None,
                "task_type": oem.task_type if oem else None,
                "oem_intervals_json": oem.intervals_json if oem else None,
                "amp_intervals_json": amp.intervals_json or {},
                "oem_raw_interval_text": oem.raw_interval_text if oem else None,
                "effectivity_expression_json": amp.effectivity_expression_json or {},
                "raw_effectivity_text": oem.raw_effectivity_text if oem else None,
                "source_requirements_json": oem.source_requirements_json if oem else [],
                "source_reference": amp.source_reference,
                "source_revision": oem.source_revision if oem else None,
                "source_page_ref": oem.source_page_ref if oem else None,
                "justification": amp.justification,
                "approval_reference": amp.approval_reference,
                "is_mandatory": overlay._is_mandatory(oem) if oem else False,
                "comparison_state": state,
            }
        )
    return {"total": total, "offset": offset, "limit": limit, "items": items, "counts": counts}
