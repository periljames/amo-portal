from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.aircraft_architecture.content_packs import models as content_models
from amodb.database import get_db
from amodb.security import get_current_active_user, require_roles

from . import models, overlay, schemas, services

router = APIRouter(prefix="/programmes", tags=["tenant maintenance programmes"])

PROGRAMME_WRITE_ROLES = ("SUPERUSER", "AMO_ADMIN", "PLANNING_ENGINEER")


def _amo_id(user: account_models.User) -> str:
    value = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return str(value)


def _programme(db: Session, programme_id: str, user: account_models.User) -> models.TenantMaintenanceProgramme:
    row = db.get(models.TenantMaintenanceProgramme, programme_id)
    if not row or str(row.amo_id) != _amo_id(user):
        raise HTTPException(status_code=404, detail="Programme not found")
    return row


def _revision(db: Session, revision_id: str, user: account_models.User) -> models.TenantProgrammeRevision:
    row = (
        db.query(models.TenantProgrammeRevision)
        .options(selectinload(models.TenantProgrammeRevision.tasks))
        .filter(models.TenantProgrammeRevision.id == revision_id)
        .first()
    )
    if not row or str(row.programme.amo_id) != _amo_id(user):
        raise HTTPException(status_code=404, detail="Programme revision not found")
    return row


def _require_draft(revision: models.TenantProgrammeRevision) -> None:
    if revision.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Published, superseded and withdrawn AMP revisions are immutable")


def _recompute_hash(db: Session, revision: models.TenantProgrammeRevision) -> None:
    """Hash the authoritative persisted draft, never a stale relationship cache."""
    db.flush()
    db.expire(revision, ["tasks"])
    revision.content_hash = services.recompute_revision_hash(revision)
    db.add(revision)


@router.get("", response_model=list[schemas.ProgrammeRead])
def list_programmes(
    status_filter: str | None = Query(default="ACTIVE", alias="status"),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    query = db.query(models.TenantMaintenanceProgramme).filter(
        models.TenantMaintenanceProgramme.amo_id == _amo_id(user)
    )
    if status_filter:
        query = query.filter(models.TenantMaintenanceProgramme.status == status_filter.upper())
    return query.order_by(models.TenantMaintenanceProgramme.code).all()


@router.post("", response_model=schemas.ProgrammeRead, status_code=201)
def create_programme(
    payload: schemas.ProgrammeCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    amo_id = _amo_id(user)
    duplicate = db.query(models.TenantMaintenanceProgramme.id).filter(
        models.TenantMaintenanceProgramme.amo_id == amo_id,
        models.TenantMaintenanceProgramme.code == payload.code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Programme code already exists")
    row = models.TenantMaintenanceProgramme(
        amo_id=amo_id,
        **payload.model_dump(),
        created_by_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{programme_id}/revisions", response_model=list[schemas.RevisionRead])
def list_revisions(
    programme_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    programme = _programme(db, programme_id, user)
    return (
        db.query(models.TenantProgrammeRevision)
        .filter(models.TenantProgrammeRevision.programme_id == programme.id)
        .order_by(models.TenantProgrammeRevision.created_at.desc())
        .all()
    )


@router.get("/revisions/{revision_id}", response_model=schemas.RevisionDetailRead)
def get_revision(
    revision_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return _revision(db, revision_id, user)


@router.get("/baseline-resolution", response_model=schemas.BaselineResolutionRead)
def baseline_resolution(
    aircraft_type_revision_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return overlay.resolve_oem_baseline(db, aircraft_type_revision_id=aircraft_type_revision_id)


@router.get("/aircraft-defaults", response_model=dict)
def aircraft_defaults(
    aircraft_type_revision_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    resolution = overlay.resolve_oem_baseline(db, aircraft_type_revision_id=aircraft_type_revision_id)
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
    programme_candidates = [
        {
            "programme_id": row.programme_id,
            "programme_code": row.programme.code,
            "programme_title": row.programme.title,
            "revision_id": row.id,
            "revision_code": row.revision_code,
            "base_content_pack_revision_id": row.base_content_pack_revision_id,
            "content_hash": row.content_hash,
        }
        for row in published
    ]
    exact_oem = resolution["state"] == "RESOLVED"
    state = "RESOLVED" if len(programme_candidates) == 1 and exact_oem else "AMBIGUOUS" if len(programme_candidates) > 1 else "NO_TENANT_AMP"
    return {
        "state": state,
        "requires_series_confirmation": resolution["state"] == "CONFIRM_DERIVED_SERIES",
        "oem": resolution,
        "programme_candidates": programme_candidates,
        "selected_programme_revision_id": programme_candidates[0]["revision_id"] if state == "RESOLVED" else None,
    }


@router.post("/{programme_id}/revisions", response_model=schemas.RevisionRead, status_code=201)
def create_revision(
    programme_id: str,
    payload: schemas.RevisionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    """Compatibility route for existing callers.

    Manually supplied tasks are deliberately marked LEGACY and cannot be
    published until reconciled through the OEM overlay workflow.
    """
    programme = _programme(db, programme_id, user)
    task_dicts = [
        {
            **task.model_dump(),
            "decision": "LEGACY",
            "source_content_task_id": None,
            "source_task_hash": None,
            "justification": None,
            "approval_reference": None,
        }
        for task in payload.tasks
    ]
    content_hash = services.programme_revision_hash(
        programme.code,
        payload.revision_code,
        payload.aircraft_type_revision_id,
        payload.effectivity_rule_version_id,
        payload.source_reference,
        payload.source_revision,
        task_dicts,
        payload.base_content_pack_revision_id,
    )
    values = payload.model_dump(exclude={"tasks"})
    if values.get("source_checksum_sha256"):
        values["source_checksum_sha256"] = values["source_checksum_sha256"].lower()
    revision = models.TenantProgrammeRevision(
        programme_id=programme.id,
        **values,
        content_hash=content_hash,
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()
    for task in task_dicts:
        db.add(models.TenantProgrammeTask(revision_id=revision.id, **task))
    db.commit()
    db.refresh(revision)
    return revision


@router.post("/{programme_id}/revisions/from-oem", response_model=schemas.RevisionDetailRead, status_code=201)
def create_revision_from_oem(
    programme_id: str,
    payload: schemas.CreateFromOemRequest,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    programme = _programme(db, programme_id, user)
    resolution = overlay.resolve_oem_baseline(db, aircraft_type_revision_id=payload.aircraft_type_revision_id)
    if resolution["state"] == "CONFIRM_DERIVED_SERIES" and not payload.confirm_derived_series:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Aircraft series was derived from the model identity and must be confirmed once before creating the AMP draft",
                "resolution": resolution,
            },
        )
    candidates = {row["revision_id"]: row for row in resolution["candidates"]}
    baseline_id = payload.base_content_pack_revision_id
    if not baseline_id:
        if len(candidates) != 1:
            raise HTTPException(status_code=409, detail={"message": "OEM baseline is not uniquely resolved", "resolution": resolution})
        baseline_id = next(iter(candidates))
    if baseline_id not in candidates:
        raise HTTPException(status_code=409, detail={"message": "Selected OEM baseline does not match the aircraft type/series", "resolution": resolution})

    baseline = (
        db.query(content_models.AircraftContentPackRevision)
        .options(
            selectinload(content_models.AircraftContentPackRevision.tasks),
            selectinload(content_models.AircraftContentPackRevision.sources),
        )
        .filter(content_models.AircraftContentPackRevision.id == baseline_id)
        .first()
    )
    if not baseline or baseline.status != "PUBLISHED" or not baseline.content_hash:
        raise HTTPException(status_code=409, detail="Selected OEM baseline is not a published controlled revision")

    duplicate = db.query(models.TenantProgrammeRevision.id).filter(
        models.TenantProgrammeRevision.programme_id == programme.id,
        models.TenantProgrammeRevision.revision_code == payload.revision_code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Programme revision code already exists")

    source_reference = baseline.pack.code
    source_revision = baseline.revision_code
    revision = models.TenantProgrammeRevision(
        programme_id=programme.id,
        revision_code=payload.revision_code,
        aircraft_type_revision_id=payload.aircraft_type_revision_id,
        effectivity_rule_version_id=payload.effectivity_rule_version_id,
        base_content_pack_revision_id=baseline.id,
        source_reference=source_reference,
        source_revision=source_revision,
        source_checksum_sha256=baseline.content_hash,
        change_summary=payload.change_summary,
        supersedes_revision_id=payload.supersedes_revision_id,
        created_by_user_id=user.id,
    )
    db.add(revision)
    db.flush()

    for oem in baseline.tasks:
        db.add(
            models.TenantProgrammeTask(
                revision_id=revision.id,
                source_content_task_id=oem.id,
                decision="INHERIT",
                task_code=oem.task_code,
                title=oem.title,
                ata_chapter=oem.ata_chapter,
                intervals_json=oem.intervals_json,
                effectivity_expression_json=oem.effectivity_expression_json or {},
                source_reference=oem.source_reference,
                source_task_hash=overlay.task_source_hash(oem),
                metadata_json={
                    "oem_programme_section": oem.programme_section,
                    "oem_task_type": oem.task_type,
                    "raw_interval_text": oem.raw_interval_text,
                    "raw_effectivity_text": oem.raw_effectivity_text,
                    "source_requirements_json": oem.source_requirements_json or [],
                    "task_card_number": oem.task_card_number,
                    "task_card_configuration": oem.task_card_configuration,
                    "amm_reference": oem.amm_reference,
                    "source_revision": oem.source_revision,
                    "source_checksum_sha256": oem.source_checksum_sha256,
                    "source_page_ref": oem.source_page_ref,
                },
            )
        )
    _recompute_hash(db, revision)
    db.commit()
    db.refresh(revision)
    return _revision(db, revision.id, user)


@router.patch("/revisions/{revision_id}/tasks/{task_id}", response_model=schemas.TaskRead)
def update_task_decision(
    revision_id: str,
    task_id: str,
    payload: schemas.TaskDecisionUpdate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    revision = _revision(db, revision_id, user)
    _require_draft(revision)
    task = next((row for row in revision.tasks if row.id == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="AMP task not found")
    if not task.source_content_task_id:
        raise HTTPException(status_code=409, detail="Operator-added tasks are not editable through the OEM decision endpoint")
    oem = db.get(content_models.AircraftContentPackTask, task.source_content_task_id)
    if not oem or oem.revision_id != revision.base_content_pack_revision_id:
        raise HTTPException(status_code=409, detail="OEM task lineage is no longer valid for this AMP draft")

    if payload.decision == "INHERIT":
        task.decision = "INHERIT"
        task.intervals_json = oem.intervals_json
        task.effectivity_expression_json = oem.effectivity_expression_json or {}
        task.justification = None
        task.approval_reference = payload.approval_reference
    else:
        intervals = payload.intervals_json or task.intervals_json
        okay, reasons = overlay.compare_interval_strictness(oem.intervals_json or {}, intervals or {})
        if not okay:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Tenant AMP may be equal to or more restrictive than the OEM requirement, never less restrictive",
                    "code": "AMP_EXCEEDS_OEM_LIMIT",
                    "reasons": reasons,
                    "oem_intervals": oem.intervals_json,
                    "proposed_intervals": intervals,
                },
            )
        if not (payload.justification or "").strip():
            raise HTTPException(status_code=422, detail="A controlled justification is required when the AMP tightens an OEM interval")
        task.decision = "TIGHTEN"
        task.intervals_json = intervals
        task.effectivity_expression_json = oem.effectivity_expression_json or {}
        task.justification = payload.justification.strip()
        task.approval_reference = payload.approval_reference
    task.source_task_hash = overlay.task_source_hash(oem)
    db.add(task)
    _recompute_hash(db, revision)
    db.commit()
    db.refresh(task)
    return task


@router.post("/revisions/{revision_id}/tasks", response_model=schemas.TaskRead, status_code=201)
def add_operator_task(
    revision_id: str,
    payload: schemas.OperatorTaskCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    revision = _revision(db, revision_id, user)
    _require_draft(revision)
    duplicate = db.query(models.TenantProgrammeTask.id).filter(
        models.TenantProgrammeTask.revision_id == revision.id,
        models.TenantProgrammeTask.task_code == payload.task_code,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Task code already exists in this AMP revision")
    row = models.TenantProgrammeTask(
        revision_id=revision.id,
        source_content_task_id=None,
        decision="ADD",
        task_code=payload.task_code,
        title=payload.title,
        ata_chapter=payload.ata_chapter,
        intervals_json=payload.intervals_json,
        effectivity_expression_json=payload.effectivity_expression_json,
        source_reference=payload.source_reference,
        justification=payload.justification.strip(),
        approval_reference=payload.approval_reference,
        source_task_hash=None,
        metadata_json=payload.metadata_json,
    )
    db.add(row)
    _recompute_hash(db, revision)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/revisions/{revision_id}/tasks/{task_id}", status_code=204)
def delete_operator_task(
    revision_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    revision = _revision(db, revision_id, user)
    _require_draft(revision)
    task = next((row for row in revision.tasks if row.id == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="AMP task not found")
    if task.decision != "ADD" or task.source_content_task_id:
        raise HTTPException(status_code=409, detail="OEM-derived requirements cannot be deleted; use INHERIT or TIGHTEN")
    db.delete(task)
    _recompute_hash(db, revision)
    db.commit()
    return Response(status_code=204)


@router.post("/revisions/{revision_id}/validate", response_model=schemas.ValidationRead)
def validate_revision(
    revision_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    revision = _revision(db, revision_id, user)
    _recompute_hash(db, revision)
    result = overlay.validate_revision(db, revision)
    baseline = result.pop("baseline", None)
    if not baseline or not baseline.content_hash:
        db.rollback()
        return result
    run = services.persist_validation_run(
        db,
        revision=revision,
        baseline_content_hash=baseline.content_hash,
        result=result,
        actor_id=user.id,
    )
    db.commit()
    return {**result, "validation_run_id": run.id}


@router.get("/revisions/{revision_id}/validation-runs", response_model=list[schemas.ValidationRunRead])
def validation_runs(
    revision_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    revision = _revision(db, revision_id, user)
    return (
        db.query(models.TenantProgrammeValidationRun)
        .filter(models.TenantProgrammeValidationRun.revision_id == revision.id)
        .order_by(models.TenantProgrammeValidationRun.created_at.desc())
        .limit(50)
        .all()
    )


@router.post("/revisions/{revision_id}/publish", response_model=schemas.RevisionRead)
def publish_revision(
    revision_id: str,
    payload: schemas.PublishRequest,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_roles(*PROGRAMME_WRITE_ROLES)),
):
    revision = _revision(db, revision_id, user)
    _require_draft(revision)
    current_hash = services.recompute_revision_hash(revision)
    if revision.content_hash != current_hash or current_hash != payload.expected_content_hash:
        raise HTTPException(status_code=409, detail="Programme content changed after review; validate the current draft again")

    result = overlay.ensure_revision_publishable(db, revision)
    baseline = result["baseline"]
    validation_result = {key: value for key, value in result.items() if key != "baseline"}
    services.persist_validation_run(
        db,
        revision=revision,
        baseline_content_hash=baseline.content_hash,
        result=validation_result,
        actor_id=user.id,
    )

    current = db.query(models.TenantProgrammeRevision).filter(
        models.TenantProgrammeRevision.programme_id == revision.programme_id,
        models.TenantProgrammeRevision.status == "PUBLISHED",
    ).with_for_update(of=models.TenantProgrammeRevision).all()
    for previous in current:
        previous.status = "SUPERSEDED"
        db.add(previous)

    revision.status = "PUBLISHED"
    revision.source_currentness_at_approval = str(
        validation_result.get("summary", {}).get("oem_currentness_at_validation") or "UNKNOWN"
    )
    revision.approval_reference = payload.approval_reference
    revision.published_by_user_id = user.id
    revision.published_at = datetime.now(timezone.utc)
    revision.programme.approval_reference = payload.approval_reference
    db.add(revision.programme)
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


@router.post("/upgrade-impact")
def upgrade_impact(
    payload: schemas.UpgradeImpactRequest,
    _: account_models.User = Depends(get_current_active_user),
):
    return services.build_upgrade_impact(payload.current_tasks, payload.proposed_tasks)
