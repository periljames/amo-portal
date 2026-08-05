from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.security import get_current_active_user, require_roles

from ...database import get_db
from . import ingestion, models, schemas, services
from .effectivity import evaluate_effectivity, validate_expression


router = APIRouter(prefix="/induction", tags=["aircraft_induction"])

CATALOGUE_EDITOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
)
APPROVER_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
)
INDUCTION_EDITOR_ROLES = (
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
)


def _commit(db: Session, row=None):
    db.commit()
    if row is not None:
        db.refresh(row)
    return row


@router.get("/catalogue", response_model=schemas.CatalogueRead)
def get_catalogue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return services.list_catalogue(db, current_user.effective_amo_id)


@router.post("/catalogue/families", response_model=schemas.FamilyRead, status_code=status.HTTP_201_CREATED)
def create_family(
    payload: schemas.FamilyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_family(db, payload, current_user))


@router.post("/catalogue/types", response_model=schemas.TypeRead, status_code=status.HTTP_201_CREATED)
def create_type(
    payload: schemas.TypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_type(db, payload, current_user))


@router.post("/catalogue/variants", response_model=schemas.VariantRead, status_code=status.HTTP_201_CREATED)
def create_variant(
    payload: schemas.VariantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_variant(db, payload, current_user))


@router.post("/catalogue/templates", response_model=schemas.TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: schemas.TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_template(db, payload, current_user))


@router.post("/catalogue/templates/{template_id}/revisions", response_model=schemas.TemplateRevisionRead, status_code=status.HTTP_201_CREATED)
def create_template_revision(
    template_id: str,
    payload: schemas.TemplateRevisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_template_revision(db, template_id, payload, current_user))


@router.post("/catalogue/revisions/{revision_id}/source-documents", response_model=schemas.SourceDocumentRead, status_code=status.HTTP_201_CREATED)
def add_source_document(
    revision_id: str,
    payload: schemas.SourceDocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.add_source_document(db, revision_id, payload, current_user))


@router.post("/catalogue/revisions/{revision_id}/configuration", response_model=schemas.ConfigurationNodeRead, status_code=status.HTTP_201_CREATED)
def add_configuration_node(
    revision_id: str,
    payload: schemas.ConfigurationNodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.add_configuration_node(db, revision_id, payload, current_user))


@router.post("/catalogue/revisions/{revision_id}/requirements", response_model=schemas.RequirementRead, status_code=status.HTTP_201_CREATED)
def add_requirement(
    revision_id: str,
    payload: schemas.RequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.add_requirement(db, revision_id, payload, current_user))


@router.post("/catalogue/revisions/{revision_id}/publish", response_model=schemas.TemplateRevisionRead)
def publish_revision(
    revision_id: str,
    payload: schemas.PublishRevisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    return _commit(db, services.publish_revision(db, revision_id, payload, current_user))


@router.post("/effectivity/evaluate", response_model=schemas.EffectivityEvaluationRead)
def evaluate_expression(
    payload: schemas.EffectivityEvaluationRequest,
    current_user: User = Depends(get_current_active_user),
):
    del current_user
    errors = validate_expression(payload.expression)
    if errors:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EFFECTIVITY", "errors": errors})
    result = evaluate_effectivity(payload.expression, payload.context)
    return schemas.EffectivityEvaluationRead(applicable=result.applicable, explanations=result.explanations)


@router.get("/mapping-profiles", response_model=list[schemas.MappingProfileRead])
def list_mapping_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return services.list_mapping_profiles(db, current_user.effective_amo_id)


@router.post("/mapping-profiles", response_model=schemas.MappingProfileRead, status_code=status.HTTP_201_CREATED)
def create_mapping_profile(
    payload: schemas.MappingProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_mapping_profile(db, payload, current_user))


@router.get("/programs", response_model=list[schemas.TenantProgramRead])
def list_programs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return services.list_tenant_programs(db, current_user.effective_amo_id)


@router.post("/programs", response_model=schemas.TenantProgramRead, status_code=status.HTTP_201_CREATED)
def create_program(
    payload: schemas.TenantProgramCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_tenant_program(db, payload, current_user))


@router.post("/programs/{program_id}/revisions", response_model=schemas.TenantProgramRevisionRead, status_code=status.HTTP_201_CREATED)
def create_program_revision(
    program_id: str,
    payload: schemas.TenantProgramRevisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.create_tenant_program_revision(db, program_id, payload, current_user))


@router.post("/program-revisions/{revision_id}/overrides", response_model=schemas.ProgramOverrideRead, status_code=status.HTTP_201_CREATED)
def add_program_override(
    revision_id: str,
    payload: schemas.ProgramOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CATALOGUE_EDITOR_ROLES)),
):
    return _commit(db, services.add_program_override(db, revision_id, payload, current_user))


@router.post("/program-revisions/{revision_id}/approve", response_model=schemas.TenantProgramRevisionRead)
def approve_program_revision(
    revision_id: str,
    payload: schemas.ApproveProgramRevisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    return _commit(db, services.approve_program_revision(db, revision_id, payload, current_user))


@router.get("/jobs", response_model=list[schemas.InductionRead])
def list_inductions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return services.list_inductions(db, current_user.effective_amo_id)


@router.post("/jobs", response_model=schemas.InductionRead, status_code=status.HTTP_201_CREATED)
def create_induction(
    payload: schemas.InductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INDUCTION_EDITOR_ROLES)),
):
    return _commit(db, services.create_induction(db, payload, current_user))


@router.get("/jobs/{induction_id}", response_model=schemas.InductionWorkspaceRead)
def get_induction_workspace(
    induction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    return services.workspace(db, induction)


@router.post("/jobs/{induction_id}/stage", response_model=list[schemas.DatasetRead])
def stage_json_dataset(
    induction_id: str,
    payload: schemas.StagedRow,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INDUCTION_EDITOR_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    parsed = ingestion.ParsedDataset(
        dataset=payload.dataset,
        source_name=payload.source_name,
        source_sheet=payload.source_sheet,
        headers=payload.headers,
        rows=payload.rows,
        fingerprint=payload.fingerprint,
    )
    created = services.stage_parsed_datasets(db, induction, [parsed], current_user)
    db.commit()
    return [schemas.DatasetRead.model_validate(item) for item in created]


@router.post("/jobs/{induction_id}/upload", response_model=list[schemas.DatasetRead])
async def upload_sources(
    induction_id: str,
    files: Annotated[list[UploadFile], File(...)],
    source_system: Annotated[str, Form()] = "GENERIC",
    dataset: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INDUCTION_EDITOR_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    parsed: list[ingestion.ParsedDataset] = []
    for file in files:
        parsed.extend(await ingestion.parse_upload(file, source_system=source_system, requested_dataset=dataset))
    created = services.stage_parsed_datasets(db, induction, parsed, current_user)
    db.commit()
    return [schemas.DatasetRead.model_validate(item) for item in created]


@router.post("/jobs/{induction_id}/validate", response_model=schemas.InductionRead)
def validate_induction(
    induction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INDUCTION_EDITOR_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    services.validate_induction_rows(db, induction, current_user)
    db.commit()
    db.refresh(induction)
    return induction


@router.post("/jobs/{induction_id}/rows/{row_id}/decision", response_model=schemas.RowRead)
def decide_row(
    induction_id: str,
    row_id: str,
    payload: schemas.RowDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INDUCTION_EDITOR_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    row = services.decide_row(db, induction, row_id, payload, current_user)
    return _commit(db, row)


@router.post("/jobs/{induction_id}/resolve-effectivity", response_model=schemas.ApplicabilitySnapshotRead)
def resolve_effectivity(
    induction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INDUCTION_EDITOR_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    snapshot = services.resolve_applicability(db, induction, current_user)
    return _commit(db, snapshot)


@router.post("/jobs/{induction_id}/approve", response_model=schemas.InductionRead)
def approve_induction(
    induction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    return _commit(db, services.approve_induction(db, induction, current_user))


@router.post("/jobs/{induction_id}/activate", response_model=schemas.BindingRead)
def activate_induction(
    induction_id: str,
    payload: schemas.ActivationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    induction = services.get_induction(db, induction_id, current_user.effective_amo_id)
    binding = services.activate_induction(db, induction, payload, current_user)
    return _commit(db, binding)
