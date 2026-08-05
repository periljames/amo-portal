from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts.models import User
from amodb.security import get_current_active_user

from ...database import get_db
from . import models, schemas


router = APIRouter()


@router.get("/catalogue/revisions/{revision_id}")
def get_template_revision_workspace(
    revision_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    revision = (
        db.query(models.AircraftTypeTemplateRevision)
        .options(
            selectinload(models.AircraftTypeTemplateRevision.source_documents),
            selectinload(models.AircraftTypeTemplateRevision.configuration_nodes),
            selectinload(models.AircraftTypeTemplateRevision.requirements),
        )
        .join(models.AircraftTypeTemplate)
        .filter(
            models.AircraftTypeTemplateRevision.id == revision_id,
            (models.AircraftTypeTemplate.visibility == "GLOBAL")
            | (models.AircraftTypeTemplate.owner_amo_id == current_user.effective_amo_id),
        )
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Template revision not found")
    return {
        "revision": schemas.TemplateRevisionRead.model_validate(revision),
        "source_documents": [schemas.SourceDocumentRead.model_validate(item) for item in revision.source_documents],
        "configuration_nodes": [schemas.ConfigurationNodeRead.model_validate(item) for item in revision.configuration_nodes],
        "requirements": [schemas.RequirementRead.model_validate(item) for item in revision.requirements],
    }


@router.get("/programs/{program_id}/revisions", response_model=list[schemas.TenantProgramRevisionRead])
def list_program_revisions(
    program_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    program = db.query(models.TenantMaintenanceProgram).filter(
        models.TenantMaintenanceProgram.id == program_id,
        models.TenantMaintenanceProgram.amo_id == current_user.effective_amo_id,
    ).first()
    if not program:
        raise HTTPException(status_code=404, detail="Tenant maintenance programme not found")
    return (
        db.query(models.TenantMaintenanceProgramRevision)
        .filter(models.TenantMaintenanceProgramRevision.program_id == program_id)
        .order_by(models.TenantMaintenanceProgramRevision.created_at.desc())
        .all()
    )
