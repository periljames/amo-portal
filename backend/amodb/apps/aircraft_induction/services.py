from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts.models import User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.fleet import models as fleet_models
from amodb.apps.maintenance_program import models as amp_models
from amodb.apps.maintenance_program import revision_models as amp_revision_models

from . import models, schemas
from .effectivity import evaluate_effectivity, validate_expression
from .ingestion import ParsedDataset, normalize_header


REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "AIRCRAFT_MASTER": ("serial_number", "registration"),
    "CONFIGURATION": ("position",),
    "COMPONENTS": ("position",),
    "LLP_STATUS": ("part_number",),
    "UTILISATION": ("date",),
    "AMP_STATUS": ("task_code",),
    "AD_STATUS": ("ad_number",),
    "SB_STATUS": ("sb_number",),
    "MODIFICATIONS": ("modification_reference",),
    "REPAIRS": ("repair_reference",),
    "DEFERRALS": ("deferral_reference",),
    "MAINTENANCE_HISTORY": ("reference",),
    "DOCUMENT_INDEX": ("reference",),
}

NUMERIC_FIELDS = {
    "total_hours", "total_cycles", "current_hours", "current_cycles", "installed_hours",
    "installed_cycles", "life_limit_hours", "life_limit_cycles", "remaining_hours",
    "remaining_cycles", "last_done_hours", "last_done_cycles", "next_due_hours",
    "next_due_cycles", "flight_hours", "flight_cycles",
}

DATE_FIELDS = {
    "date", "installed_date", "removed_date", "last_done_date", "next_due_date",
    "effective_date", "compliance_date", "due_date", "issued_on", "expires_on",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


def _conflict(message: str, code: str = "CONFLICT") -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": message})


def _audit(db: Session, *, amo_id: str, actor: User, entity_type: str, entity_id: str, action: str, after: dict[str, Any] | None = None) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor.id,
            before_json=None,
            after_json=after,
        ),
    )


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def list_catalogue(db: Session, amo_id: str) -> schemas.CatalogueRead:
    families = db.query(models.AircraftFamily).filter(models.AircraftFamily.status == "ACTIVE").order_by(models.AircraftFamily.manufacturer, models.AircraftFamily.name).all()
    types = db.query(models.AircraftType).filter(models.AircraftType.status == "ACTIVE").order_by(models.AircraftType.name).all()
    variants = db.query(models.AircraftVariant).filter(models.AircraftVariant.status == "ACTIVE").order_by(models.AircraftVariant.model_code).all()
    templates = (
        db.query(models.AircraftTypeTemplate)
        .filter(
            models.AircraftTypeTemplate.status == "ACTIVE",
            or_(
                models.AircraftTypeTemplate.visibility == "GLOBAL",
                models.AircraftTypeTemplate.owner_amo_id == amo_id,
            ),
        )
        .order_by(models.AircraftTypeTemplate.code)
        .all()
    )
    template_ids = [item.id for item in templates]
    revisions = []
    if template_ids:
        revisions = (
            db.query(models.AircraftTypeTemplateRevision)
            .filter(models.AircraftTypeTemplateRevision.template_id.in_(template_ids))
            .order_by(models.AircraftTypeTemplateRevision.template_id, models.AircraftTypeTemplateRevision.created_at.desc())
            .all()
        )
    return schemas.CatalogueRead(
        families=[schemas.FamilyRead.model_validate(item) for item in families],
        types=[schemas.TypeRead.model_validate(item) for item in types],
        variants=[schemas.VariantRead.model_validate(item) for item in variants],
        templates=[schemas.TemplateRead.model_validate(item) for item in templates],
        revisions=[schemas.TemplateRevisionRead.model_validate(item) for item in revisions],
    )


def create_family(db: Session, payload: schemas.FamilyCreate, actor: User) -> models.AircraftFamily:
    code = payload.code.strip().upper()
    if db.query(models.AircraftFamily).filter(models.AircraftFamily.code == code).first():
        raise _conflict(f"Aircraft family {code} already exists", "FAMILY_EXISTS")
    row = models.AircraftFamily(code=code, name=payload.name.strip(), manufacturer=payload.manufacturer.strip(), description=payload.description)
    db.add(row)
    db.flush()
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftFamily", entity_id=row.id, action="create", after={"code": row.code})
    return row


def create_type(db: Session, payload: schemas.TypeCreate, actor: User) -> models.AircraftType:
    if not db.get(models.AircraftFamily, payload.family_id):
        raise _not_found("Aircraft family")
    code = payload.type_code.strip().upper()
    existing = db.query(models.AircraftType).filter(models.AircraftType.family_id == payload.family_id, models.AircraftType.type_code == code).first()
    if existing:
        raise _conflict(f"Aircraft type {code} already exists", "TYPE_EXISTS")
    row = models.AircraftType(
        family_id=payload.family_id,
        type_code=code,
        name=payload.name.strip(),
        type_certificate_number=payload.type_certificate_number,
        authority=payload.authority,
        description=payload.description,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftType", entity_id=row.id, action="create", after={"type_code": row.type_code})
    return row


def create_variant(db: Session, payload: schemas.VariantCreate, actor: User) -> models.AircraftVariant:
    if not db.get(models.AircraftType, payload.aircraft_type_id):
        raise _not_found("Aircraft type")
    code = payload.variant_code.strip().upper()
    existing = db.query(models.AircraftVariant).filter(models.AircraftVariant.aircraft_type_id == payload.aircraft_type_id, models.AircraftVariant.variant_code == code).first()
    if existing:
        raise _conflict(f"Aircraft variant {code} already exists", "VARIANT_EXISTS")
    row = models.AircraftVariant(
        aircraft_type_id=payload.aircraft_type_id,
        variant_code=code,
        model_code=payload.model_code.strip().upper(),
        marketing_name=payload.marketing_name,
        description=payload.description,
        serial_effectivity_json=payload.serial_effectivity_json,
        engine_options_json=payload.engine_options_json,
        propeller_options_json=payload.propeller_options_json,
        apu_options_json=payload.apu_options_json,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftVariant", entity_id=row.id, action="create", after={"variant_code": row.variant_code})
    return row


def create_template(db: Session, payload: schemas.TemplateCreate, actor: User) -> models.AircraftTypeTemplate:
    if not db.get(models.AircraftVariant, payload.variant_id):
        raise _not_found("Aircraft variant")
    code = payload.code.strip().upper()
    if db.query(models.AircraftTypeTemplate).filter(models.AircraftTypeTemplate.code == code).first():
        raise _conflict(f"Aircraft type template {code} already exists", "TEMPLATE_EXISTS")
    row = models.AircraftTypeTemplate(
        variant_id=payload.variant_id,
        code=code,
        title=payload.title.strip(),
        visibility=payload.visibility,
        owner_amo_id=actor.effective_amo_id if payload.visibility == "TENANT" else None,
        description=payload.description,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftTypeTemplate", entity_id=row.id, action="create", after={"code": row.code, "visibility": row.visibility})
    return row


def _visible_template(db: Session, template_id: str, amo_id: str) -> models.AircraftTypeTemplate:
    row = (
        db.query(models.AircraftTypeTemplate)
        .filter(
            models.AircraftTypeTemplate.id == template_id,
            or_(models.AircraftTypeTemplate.visibility == "GLOBAL", models.AircraftTypeTemplate.owner_amo_id == amo_id),
        )
        .first()
    )
    if not row:
        raise _not_found("Aircraft type template")
    return row


def create_template_revision(db: Session, template_id: str, payload: schemas.TemplateRevisionCreate, actor: User) -> models.AircraftTypeTemplateRevision:
    _visible_template(db, template_id, actor.effective_amo_id)
    if db.query(models.AircraftTypeTemplateRevision).filter(models.AircraftTypeTemplateRevision.template_id == template_id, models.AircraftTypeTemplateRevision.revision_code == payload.revision_code).first():
        raise _conflict(f"Template revision {payload.revision_code} already exists", "REVISION_EXISTS")
    row = models.AircraftTypeTemplateRevision(
        template_id=template_id,
        revision_code=payload.revision_code.strip().upper(),
        effective_date=payload.effective_date,
        source_reference=payload.source_reference,
        source_hash=payload.source_hash,
        release_notes=payload.release_notes,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftTypeTemplateRevision", entity_id=row.id, action="create", after={"revision_code": row.revision_code})
    return row


def _draft_revision(db: Session, revision_id: str, amo_id: str) -> models.AircraftTypeTemplateRevision:
    row = (
        db.query(models.AircraftTypeTemplateRevision)
        .join(models.AircraftTypeTemplate)
        .filter(
            models.AircraftTypeTemplateRevision.id == revision_id,
            or_(models.AircraftTypeTemplate.visibility == "GLOBAL", models.AircraftTypeTemplate.owner_amo_id == amo_id),
        )
        .first()
    )
    if not row:
        raise _not_found("Template revision")
    if row.status != "DRAFT":
        raise _conflict("Published template revisions are immutable", "REVISION_IMMUTABLE")
    return row


def add_source_document(db: Session, revision_id: str, payload: schemas.SourceDocumentCreate, actor: User) -> models.TemplateSourceDocument:
    _draft_revision(db, revision_id, actor.effective_amo_id)
    row = models.TemplateSourceDocument(revision_id=revision_id, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


def add_configuration_node(db: Session, revision_id: str, payload: schemas.ConfigurationNodeCreate, actor: User) -> models.TemplateConfigurationNode:
    revision = _draft_revision(db, revision_id, actor.effective_amo_id)
    errors = validate_expression(payload.effectivity_json)
    if errors:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EFFECTIVITY", "errors": errors})
    if payload.parent_node_key:
        parent = db.query(models.TemplateConfigurationNode).filter(models.TemplateConfigurationNode.revision_id == revision.id, models.TemplateConfigurationNode.node_key == payload.parent_node_key).first()
        if not parent:
            raise HTTPException(status_code=422, detail=f"Parent configuration node {payload.parent_node_key} does not exist in this revision")
    row = models.TemplateConfigurationNode(revision_id=revision.id, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


def add_requirement(db: Session, revision_id: str, payload: schemas.RequirementCreate, actor: User) -> models.TemplateRequirement:
    revision = _draft_revision(db, revision_id, actor.effective_amo_id)
    errors = validate_expression(payload.effectivity_json)
    if errors:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EFFECTIVITY", "errors": errors})
    if payload.source_document_id:
        source = db.query(models.TemplateSourceDocument).filter(models.TemplateSourceDocument.id == payload.source_document_id, models.TemplateSourceDocument.revision_id == revision.id).first()
        if not source:
            raise HTTPException(status_code=422, detail="Source document does not belong to this template revision")
    row = models.TemplateRequirement(revision_id=revision.id, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


def _revision_content(revision: models.AircraftTypeTemplateRevision) -> dict[str, Any]:
    return {
        "template_id": revision.template_id,
        "revision_code": revision.revision_code,
        "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
        "sources": sorted([
            {
                "type": row.document_type,
                "reference": row.reference,
                "revision": row.revision,
                "content_hash": row.content_hash,
            }
            for row in revision.source_documents
        ], key=lambda item: (item["type"], item["reference"], item.get("revision") or "")),
        "configuration": sorted([
            {
                "key": row.node_key,
                "parent": row.parent_node_key,
                "type": row.node_type,
                "position": row.position_code,
                "title": row.title,
                "allowable_parts": row.allowable_parts_json,
                "counter_rules": row.counter_rules_json,
                "effectivity": row.effectivity_json,
            }
            for row in revision.configuration_nodes
        ], key=lambda item: item["key"]),
        "requirements": sorted([
            {
                "key": row.requirement_key,
                "category": row.category,
                "ata": row.ata_chapter,
                "task_code": row.task_code,
                "title": row.title,
                "governing_logic": row.governing_logic,
                "interval": row.interval_json,
                "threshold": row.threshold_json,
                "effectivity": row.effectivity_json,
                "mandatory": row.mandatory,
            }
            for row in revision.requirements
        ], key=lambda item: item["key"]),
    }


def publish_revision(db: Session, revision_id: str, payload: schemas.PublishRevisionRequest, actor: User) -> models.AircraftTypeTemplateRevision:
    revision = (
        db.query(models.AircraftTypeTemplateRevision)
        .options(
            selectinload(models.AircraftTypeTemplateRevision.source_documents),
            selectinload(models.AircraftTypeTemplateRevision.configuration_nodes),
            selectinload(models.AircraftTypeTemplateRevision.requirements),
        )
        .filter(models.AircraftTypeTemplateRevision.id == revision_id)
        .first()
    )
    if not revision:
        raise _not_found("Template revision")
    _visible_template(db, revision.template_id, actor.effective_amo_id)
    if revision.status != "DRAFT":
        raise _conflict("Only draft revisions can be published", "INVALID_REVISION_STATE")
    blockers: list[str] = []
    if not revision.source_documents:
        blockers.append("At least one source document is required")
    if not revision.configuration_nodes:
        blockers.append("At least one configuration node is required")
    if not revision.requirements:
        blockers.append("At least one maintenance requirement is required")
    for requirement in revision.requirements:
        blockers.extend([f"{requirement.requirement_key}: {error}" for error in validate_expression(requirement.effectivity_json)])
    if blockers:
        raise HTTPException(status_code=422, detail={"code": "REVISION_NOT_PUBLISHABLE", "blockers": blockers})
    revision.content_hash = _stable_hash(_revision_content(revision))
    revision.status = "PUBLISHED"
    revision.approved_by_user_id = actor.id
    revision.approved_at = utcnow()
    if not revision.release_notes:
        revision.release_notes = payload.approval_note
    siblings = db.query(models.AircraftTypeTemplateRevision).filter(
        models.AircraftTypeTemplateRevision.template_id == revision.template_id,
        models.AircraftTypeTemplateRevision.id != revision.id,
        models.AircraftTypeTemplateRevision.status == "PUBLISHED",
    ).all()
    for sibling in siblings:
        sibling.status = "SUPERSEDED"
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftTypeTemplateRevision", entity_id=revision.id, action="publish", after={"content_hash": revision.content_hash, "approval_note": payload.approval_note})
    return revision


def create_mapping_profile(db: Session, payload: schemas.MappingProfileCreate, actor: User) -> models.ImportMappingProfile:
    amo_id = actor.effective_amo_id if payload.scope == "TENANT" else None
    last = (
        db.query(models.ImportMappingProfile)
        .filter(models.ImportMappingProfile.scope == payload.scope, models.ImportMappingProfile.amo_id == amo_id, models.ImportMappingProfile.name == payload.name)
        .order_by(models.ImportMappingProfile.version.desc())
        .first()
    )
    row = models.ImportMappingProfile(
        amo_id=amo_id,
        scope=payload.scope,
        name=payload.name.strip(),
        version=(last.version + 1) if last else 1,
        source_system=payload.source_system.strip().upper(),
        source_version=payload.source_version,
        dataset=payload.dataset,
        fingerprint=payload.fingerprint,
        header_signature_json=payload.header_signature_json,
        mapping_json=payload.mapping_json,
        transformations_json=payload.transformations_json,
        defaults_json=payload.defaults_json,
        validation_json=payload.validation_json,
        created_by_user_id=actor.id,
    )
    if last:
        last.status = "SUPERSEDED"
    db.add(row)
    db.flush()
    return row


def list_mapping_profiles(db: Session, amo_id: str) -> list[models.ImportMappingProfile]:
    return (
        db.query(models.ImportMappingProfile)
        .filter(
            models.ImportMappingProfile.status == "ACTIVE",
            or_(models.ImportMappingProfile.scope == "GLOBAL", models.ImportMappingProfile.amo_id == amo_id),
        )
        .order_by(models.ImportMappingProfile.source_system, models.ImportMappingProfile.dataset, models.ImportMappingProfile.name)
        .all()
    )


def find_mapping_profile(db: Session, *, amo_id: str, dataset: str, fingerprint: str) -> models.ImportMappingProfile | None:
    return (
        db.query(models.ImportMappingProfile)
        .filter(
            models.ImportMappingProfile.dataset == dataset,
            models.ImportMappingProfile.fingerprint == fingerprint,
            models.ImportMappingProfile.status == "ACTIVE",
            or_(models.ImportMappingProfile.scope == "GLOBAL", models.ImportMappingProfile.amo_id == amo_id),
        )
        .order_by(models.ImportMappingProfile.amo_id.isnot(None).desc(), models.ImportMappingProfile.version.desc())
        .first()
    )


def create_tenant_program(db: Session, payload: schemas.TenantProgramCreate, actor: User) -> models.TenantMaintenanceProgram:
    if not db.get(models.AircraftVariant, payload.variant_id):
        raise _not_found("Aircraft variant")
    code = payload.code.strip().upper()
    if db.query(models.TenantMaintenanceProgram).filter(models.TenantMaintenanceProgram.amo_id == actor.effective_amo_id, models.TenantMaintenanceProgram.code == code).first():
        raise _conflict(f"Tenant programme {code} already exists", "PROGRAM_EXISTS")
    row = models.TenantMaintenanceProgram(
        amo_id=actor.effective_amo_id,
        variant_id=payload.variant_id,
        code=code,
        title=payload.title,
        authority=payload.authority,
        approval_reference=payload.approval_reference,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def list_tenant_programs(db: Session, amo_id: str) -> list[models.TenantMaintenanceProgram]:
    return db.query(models.TenantMaintenanceProgram).filter(models.TenantMaintenanceProgram.amo_id == amo_id).order_by(models.TenantMaintenanceProgram.code).all()


def create_tenant_program_revision(db: Session, program_id: str, payload: schemas.TenantProgramRevisionCreate, actor: User) -> models.TenantMaintenanceProgramRevision:
    program = db.query(models.TenantMaintenanceProgram).filter(models.TenantMaintenanceProgram.id == program_id, models.TenantMaintenanceProgram.amo_id == actor.effective_amo_id).first()
    if not program:
        raise _not_found("Tenant maintenance programme")
    base = db.query(models.AircraftTypeTemplateRevision).join(models.AircraftTypeTemplate).filter(
        models.AircraftTypeTemplateRevision.id == payload.base_template_revision_id,
        models.AircraftTypeTemplateRevision.status.in_(["PUBLISHED", "SUPERSEDED"]),
        or_(models.AircraftTypeTemplate.visibility == "GLOBAL", models.AircraftTypeTemplate.owner_amo_id == actor.effective_amo_id),
    ).first()
    if not base:
        raise HTTPException(status_code=422, detail="Base aircraft-type template revision must be published and visible to the tenant")
    if base.template.variant_id != program.variant_id:
        raise HTTPException(status_code=422, detail="Base template variant does not match the tenant programme variant")
    row = models.TenantMaintenanceProgramRevision(
        program_id=program.id,
        base_template_revision_id=base.id,
        revision_code=payload.revision_code.strip().upper(),
        effective_date=payload.effective_date,
        approval_reference=payload.approval_reference,
        approval_date=payload.approval_date,
        notes=payload.notes,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def add_program_override(db: Session, revision_id: str, payload: schemas.ProgramOverrideCreate, actor: User) -> models.TenantProgramOverride:
    revision = db.query(models.TenantMaintenanceProgramRevision).join(models.TenantMaintenanceProgram).filter(
        models.TenantMaintenanceProgramRevision.id == revision_id,
        models.TenantMaintenanceProgram.amo_id == actor.effective_amo_id,
    ).first()
    if not revision:
        raise _not_found("Tenant programme revision")
    if revision.status != "DRAFT":
        raise _conflict("Approved tenant programme revisions are immutable", "PROGRAM_REVISION_IMMUTABLE")
    errors = validate_expression(payload.effectivity_json)
    if errors:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EFFECTIVITY", "errors": errors})
    row = models.TenantProgramOverride(program_revision_id=revision.id, **payload.model_dump())
    db.add(row)
    db.flush()
    return row


def approve_program_revision(db: Session, revision_id: str, payload: schemas.ApproveProgramRevisionRequest, actor: User) -> models.TenantMaintenanceProgramRevision:
    revision = db.query(models.TenantMaintenanceProgramRevision).join(models.TenantMaintenanceProgram).filter(
        models.TenantMaintenanceProgramRevision.id == revision_id,
        models.TenantMaintenanceProgram.amo_id == actor.effective_amo_id,
    ).first()
    if not revision:
        raise _not_found("Tenant programme revision")
    if revision.status != "DRAFT":
        raise _conflict("Only draft tenant programme revisions can be approved", "INVALID_PROGRAM_REVISION_STATE")
    if not revision.approval_reference or not revision.approval_date:
        raise HTTPException(status_code=422, detail="Authority approval reference and approval date are required")
    revision.status = "APPROVED"
    revision.approved_by_user_id = actor.id
    revision.approved_at = utcnow()
    if revision.notes:
        revision.notes = f"{revision.notes}\nApproval: {payload.approval_note}"
    else:
        revision.notes = f"Approval: {payload.approval_note}"
    previous = db.query(models.TenantMaintenanceProgramRevision).filter(
        models.TenantMaintenanceProgramRevision.program_id == revision.program_id,
        models.TenantMaintenanceProgramRevision.id != revision.id,
        models.TenantMaintenanceProgramRevision.status == "APPROVED",
    ).all()
    for item in previous:
        item.status = "SUPERSEDED"
    return revision


def create_induction(db: Session, payload: schemas.InductionCreate, actor: User) -> models.AircraftInduction:
    variant = db.get(models.AircraftVariant, payload.variant_id)
    if not variant:
        raise _not_found("Aircraft variant")
    template_revision = db.query(models.AircraftTypeTemplateRevision).join(models.AircraftTypeTemplate).filter(
        models.AircraftTypeTemplateRevision.id == payload.template_revision_id,
        models.AircraftTypeTemplateRevision.status.in_(["PUBLISHED", "SUPERSEDED"]),
        models.AircraftTypeTemplate.variant_id == payload.variant_id,
        or_(models.AircraftTypeTemplate.visibility == "GLOBAL", models.AircraftTypeTemplate.owner_amo_id == actor.effective_amo_id),
    ).first()
    if not template_revision:
        raise HTTPException(status_code=422, detail="Selected published type-template revision does not match the variant")
    program_revision = db.query(models.TenantMaintenanceProgramRevision).join(models.TenantMaintenanceProgram).filter(
        models.TenantMaintenanceProgramRevision.id == payload.program_revision_id,
        models.TenantMaintenanceProgramRevision.status == "APPROVED",
        models.TenantMaintenanceProgram.amo_id == actor.effective_amo_id,
        models.TenantMaintenanceProgram.variant_id == payload.variant_id,
    ).first()
    if not program_revision:
        raise HTTPException(status_code=422, detail="Selected approved tenant programme revision does not match the variant")
    if program_revision.base_template_revision_id != template_revision.id:
        raise HTTPException(status_code=422, detail="Tenant programme revision is based on a different type-template revision")
    duplicate = db.query(models.AircraftInduction).filter(
        models.AircraftInduction.amo_id == actor.effective_amo_id,
        or_(models.AircraftInduction.induction_ref == payload.induction_ref, models.AircraftInduction.serial_number == payload.serial_number),
        models.AircraftInduction.status.notin_(["CANCELLED", "ROLLED_BACK"]),
    ).first()
    if duplicate:
        raise _conflict("An active induction already exists for this reference or aircraft serial", "INDUCTION_EXISTS")
    row = models.AircraftInduction(
        amo_id=actor.effective_amo_id,
        created_by_user_id=actor.id,
        **payload.model_dump(),
    )
    db.add(row)
    db.flush()
    _audit(db, amo_id=actor.effective_amo_id, actor=actor, entity_type="AircraftInduction", entity_id=row.id, action="create", after={"induction_ref": row.induction_ref, "serial_number": row.serial_number})
    return row


def get_induction(db: Session, induction_id: str, amo_id: str) -> models.AircraftInduction:
    row = (
        db.query(models.AircraftInduction)
        .options(selectinload(models.AircraftInduction.datasets).selectinload(models.AircraftInductionDataset.rows))
        .filter(models.AircraftInduction.id == induction_id, models.AircraftInduction.amo_id == amo_id)
        .first()
    )
    if not row:
        raise _not_found("Aircraft induction")
    return row


def list_inductions(db: Session, amo_id: str) -> list[models.AircraftInduction]:
    return db.query(models.AircraftInduction).filter(models.AircraftInduction.amo_id == amo_id).order_by(models.AircraftInduction.created_at.desc()).all()


def _apply_transform(value: Any, rule: Any) -> Any:
    if value is None:
        return None
    if isinstance(rule, str):
        rule = {"type": rule}
    kind = str((rule or {}).get("type") or "").lower()
    if kind == "uppercase":
        return str(value).strip().upper()
    if kind == "lowercase":
        return str(value).strip().lower()
    if kind == "strip":
        return str(value).strip()
    if kind == "replace":
        replacements = (rule or {}).get("values") or {}
        return replacements.get(str(value), value)
    if kind == "multiply":
        return float(value) * float((rule or {}).get("factor", 1))
    return value


def normalize_row(source: dict[str, Any], profile: models.ImportMappingProfile | None) -> dict[str, Any]:
    source = {normalize_header(key): value for key, value in source.items()}
    if not profile:
        return source
    normalized = dict(profile.defaults_json or {})
    for source_field, target_field in (profile.mapping_json or {}).items():
        source_key = normalize_header(source_field)
        if target_field and source_key in source:
            normalized[str(target_field)] = source[source_key]
    for target_field, rule in (profile.transformations_json or {}).items():
        if target_field in normalized:
            normalized[target_field] = _apply_transform(normalized[target_field], rule)
    return normalized


def stage_parsed_datasets(db: Session, induction: models.AircraftInduction, parsed: Iterable[ParsedDataset], actor: User) -> list[models.AircraftInductionDataset]:
    if induction.status not in {"DRAFT", "STAGED", "VALIDATION_FAILED"}:
        raise _conflict("Datasets cannot be added after induction approval", "INDUCTION_LOCKED")
    created: list[models.AircraftInductionDataset] = []
    for item in parsed:
        profile = find_mapping_profile(db, amo_id=induction.amo_id, dataset=item.dataset, fingerprint=item.fingerprint)
        dataset = models.AircraftInductionDataset(
            induction_id=induction.id,
            dataset=item.dataset,
            source_name=item.source_name,
            source_sheet=item.source_sheet,
            fingerprint=item.fingerprint,
            mapping_profile_id=profile.id if profile else None,
            headers_json=item.headers,
            row_count=len(item.rows),
            status="STAGED" if profile else "MAPPING_REQUIRED",
        )
        db.add(dataset)
        db.flush()
        for index, source in enumerate(item.rows, start=1):
            normalized = normalize_row(source, profile)
            db.add(models.AircraftInductionRow(
                dataset_id=dataset.id,
                row_number=index,
                source_json=source,
                normalized_json=normalized,
                final_json=normalized,
                status="STAGED" if profile else "MAPPING_REQUIRED",
            ))
        created.append(dataset)
    induction.status = "STAGED"
    induction.current_step = "MAP"
    induction.counts_json = {
        "datasets": len(induction.datasets) + len(created),
        "rows": sum(item.row_count for item in induction.datasets) + sum(item.row_count for item in created),
    }
    _audit(db, amo_id=induction.amo_id, actor=actor, entity_type="AircraftInduction", entity_id=induction.id, action="stage", after=induction.counts_json)
    return created


def _parse_numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def validate_induction_rows(db: Session, induction: models.AircraftInduction, actor: User) -> dict[str, Any]:
    if not induction.datasets:
        raise HTTPException(status_code=422, detail="At least one source dataset must be staged")
    totals = {"valid": 0, "warning": 0, "invalid": 0, "mapping_required": 0}
    for dataset in induction.datasets:
        profile = db.get(models.ImportMappingProfile, dataset.mapping_profile_id) if dataset.mapping_profile_id else None
        for row in dataset.rows:
            normalized = normalize_row(row.source_json, profile)
            errors: list[str] = []
            warnings: list[str] = []
            for field in REQUIRED_FIELDS.get(dataset.dataset, ()):
                if normalized.get(field) in (None, ""):
                    errors.append(f"{field} is required")
            for field in NUMERIC_FIELDS:
                if field in normalized and normalized[field] not in (None, ""):
                    numeric = _parse_numeric(normalized[field])
                    if numeric is None:
                        errors.append(f"{field} must be numeric")
                    elif numeric < 0:
                        errors.append(f"{field} cannot be negative")
                    else:
                        normalized[field] = numeric
            for field in DATE_FIELDS:
                if field in normalized and normalized[field] not in (None, ""):
                    parsed = _parse_date(normalized[field])
                    if parsed is None:
                        errors.append(f"{field} must be a valid date")
                    else:
                        normalized[field] = parsed
            if dataset.dataset == "AIRCRAFT_MASTER":
                if str(normalized.get("serial_number") or "").strip().upper() != induction.serial_number:
                    errors.append("serial_number does not match the induction aircraft")
                if str(normalized.get("registration") or "").strip().upper() != induction.registration:
                    errors.append("registration does not match the induction aircraft")
            if dataset.dataset in {"CONFIGURATION", "COMPONENTS"} and not normalized.get("part_number"):
                warnings.append("part_number is missing; configuration effectivity may remain unresolved")
            row.normalized_json = normalized
            row.final_json = normalized if row.decision not in {"OVERRIDE", "REJECT"} else row.final_json
            row.errors_json = errors
            row.warnings_json = warnings
            if not profile:
                row.status = "MAPPING_REQUIRED"
                totals["mapping_required"] += 1
            elif errors:
                row.status = "INVALID"
                totals["invalid"] += 1
            elif warnings:
                row.status = "WARNING"
                totals["warning"] += 1
            else:
                row.status = "VALID"
                totals["valid"] += 1
        dataset.status = "INVALID" if any(row.status == "INVALID" for row in dataset.rows) else ("MAPPING_REQUIRED" if not profile else "VALIDATED")
    induction.counts_json = {**induction.counts_json, **totals}
    induction.validation_json = {"row_totals": totals}
    induction.status = "VALIDATION_FAILED" if totals["invalid"] or totals["mapping_required"] else "VALIDATED"
    induction.current_step = "VALIDATE" if induction.status == "VALIDATION_FAILED" else "EFFECTIVITY"
    _audit(db, amo_id=induction.amo_id, actor=actor, entity_type="AircraftInduction", entity_id=induction.id, action="validate", after=induction.validation_json)
    return induction.validation_json


def decide_row(db: Session, induction: models.AircraftInduction, row_id: str, payload: schemas.RowDecisionRequest, actor: User) -> models.AircraftInductionRow:
    row = db.query(models.AircraftInductionRow).join(models.AircraftInductionDataset).filter(
        models.AircraftInductionRow.id == row_id,
        models.AircraftInductionDataset.induction_id == induction.id,
    ).first()
    if not row:
        raise _not_found("Induction row")
    row.decision = payload.decision
    row.final_json = payload.final_json if payload.decision == "OVERRIDE" else ({} if payload.decision == "REJECT" else row.normalized_json)
    row.status = "REJECTED" if payload.decision == "REJECT" else "DECIDED"
    row.decided_by_user_id = actor.id
    row.decided_at = utcnow()
    return row


def _accepted_rows(induction: models.AircraftInduction, dataset_code: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for dataset in induction.datasets:
        if dataset.dataset != dataset_code:
            continue
        for row in dataset.rows:
            if row.decision == "REJECT" or row.status in {"INVALID", "MAPPING_REQUIRED"}:
                continue
            result.append(row.final_json or row.normalized_json)
    return result


def _build_context(induction: models.AircraftInduction, variant: models.AircraftVariant) -> dict[str, Any]:
    master_rows = _accepted_rows(induction, "AIRCRAFT_MASTER")
    master = master_rows[0] if master_rows else {}
    configuration = _accepted_rows(induction, "CONFIGURATION") + _accepted_rows(induction, "COMPONENTS")
    modifications = _accepted_rows(induction, "MODIFICATIONS")
    part_numbers = sorted({str(row.get("part_number")).strip().upper() for row in configuration if row.get("part_number")})
    positions = sorted({str(row.get("position")).strip().upper() for row in configuration if row.get("position")})
    embodied_modifications = sorted({
        str(row.get("modification_reference") or row.get("stc") or "").strip().upper()
        for row in modifications
        if row.get("embodied") not in {False, "NO", "N", "FALSE", 0}
    } - {""})
    return {
        "aircraft": {
            "serial_number": induction.serial_number,
            "registration": induction.registration,
            "model_code": variant.model_code,
            "variant_code": variant.variant_code,
            "msn": master.get("manufacturer_serial_number") or master.get("msn") or induction.serial_number,
            "operator_code": master.get("operator_code"),
            "home_base": master.get("home_base"),
        },
        "configuration": {
            "part_numbers": part_numbers,
            "positions": positions,
            "components": configuration,
        },
        "modifications": embodied_modifications,
        "source": {
            "system": induction.source_system,
            "reference": induction.source_reference,
        },
    }


def _apply_overrides(base_requirements: list[models.TemplateRequirement], overrides: list[models.TenantProgramOverride], context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requirements: dict[str, dict[str, Any]] = {
        item.requirement_key: {
            "requirement_key": item.requirement_key,
            "category": item.category,
            "ata_chapter": item.ata_chapter,
            "task_code": item.task_code,
            "title": item.title,
            "description": item.description,
            "governing_logic": item.governing_logic,
            "interval_json": copy.deepcopy(item.interval_json or {}),
            "threshold_json": copy.deepcopy(item.threshold_json or {}),
            "effectivity_json": copy.deepcopy(item.effectivity_json or {}),
            "source_reference": item.source_reference,
            "mandatory": item.mandatory,
            "lineage": {"base_requirement_id": item.id, "override_id": None},
        }
        for item in base_requirements
    }
    excluded_by_overlay: set[str] = set()
    for override in overrides:
        overlay_result = evaluate_effectivity(override.effectivity_json, context)
        if not overlay_result.applicable:
            continue
        if override.action == "EXCLUDE":
            excluded_by_overlay.add(override.requirement_key)
            continue
        if override.action == "ADD":
            added = copy.deepcopy(override.patch_json or {})
            added["requirement_key"] = override.requirement_key
            added.setdefault("task_code", override.requirement_key)
            added.setdefault("title", override.requirement_key)
            added.setdefault("category", "OPERATOR")
            added.setdefault("interval_json", {})
            added.setdefault("threshold_json", {})
            added.setdefault("effectivity_json", {})
            added.setdefault("mandatory", True)
            added["lineage"] = {"base_requirement_id": None, "override_id": override.id}
            requirements[override.requirement_key] = added
            continue
        target = requirements.get(override.requirement_key)
        if not target:
            raise HTTPException(status_code=422, detail=f"MODIFY override references unknown requirement {override.requirement_key}")
        target.update(copy.deepcopy(override.patch_json or {}))
        target["lineage"]["override_id"] = override.id

    applicable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for key, requirement in requirements.items():
        if key in excluded_by_overlay:
            excluded.append({**requirement, "exclusion_reason": "Excluded by approved tenant programme override"})
            continue
        result = evaluate_effectivity(requirement.get("effectivity_json"), context)
        enriched = {**requirement, "effectivity_explanations": result.explanations}
        if result.applicable:
            applicable.append(enriched)
        else:
            excluded.append({**enriched, "exclusion_reason": "Effectivity criteria did not match"})
    return applicable, excluded


def resolve_applicability(db: Session, induction: models.AircraftInduction, actor: User) -> models.AircraftApplicabilitySnapshot:
    if induction.status != "VALIDATED":
        raise _conflict("Induction must pass row validation before effectivity resolution", "VALIDATION_REQUIRED")
    variant = db.get(models.AircraftVariant, induction.variant_id)
    template_revision = (
        db.query(models.AircraftTypeTemplateRevision)
        .options(selectinload(models.AircraftTypeTemplateRevision.requirements))
        .filter(models.AircraftTypeTemplateRevision.id == induction.template_revision_id)
        .first()
    )
    program_revision = (
        db.query(models.TenantMaintenanceProgramRevision)
        .options(selectinload(models.TenantMaintenanceProgramRevision.overrides))
        .filter(models.TenantMaintenanceProgramRevision.id == induction.program_revision_id)
        .first()
    )
    if not variant or not template_revision or not program_revision:
        raise HTTPException(status_code=422, detail="Induction baseline references are incomplete")
    context = _build_context(induction, variant)
    applicable, excluded = _apply_overrides(template_revision.requirements, program_revision.overrides, context)
    configuration_hash = _stable_hash(context.get("configuration"))
    snapshot_payload = {
        "aircraft": induction.serial_number,
        "template_revision_id": template_revision.id,
        "template_content_hash": template_revision.content_hash,
        "program_revision_id": program_revision.id,
        "configuration_hash": configuration_hash,
        "applicable": applicable,
        "excluded": excluded,
    }
    snapshot = models.AircraftApplicabilitySnapshot(
        amo_id=induction.amo_id,
        induction_id=induction.id,
        aircraft_serial_number=induction.serial_number,
        template_revision_id=template_revision.id,
        program_revision_id=program_revision.id,
        configuration_hash=configuration_hash,
        snapshot_hash=_stable_hash(snapshot_payload),
        context_json=context,
        applicable_requirements_json=applicable,
        excluded_requirements_json=excluded,
    )
    db.add(snapshot)
    db.flush()
    induction.status = "EFFECTIVITY_RESOLVED"
    induction.current_step = "REVIEW"
    induction.validation_json = {
        **induction.validation_json,
        "applicability": {
            "snapshot_id": snapshot.id,
            "snapshot_hash": snapshot.snapshot_hash,
            "applicable_requirements": len(applicable),
            "excluded_requirements": len(excluded),
        },
    }
    _audit(db, amo_id=induction.amo_id, actor=actor, entity_type="AircraftInduction", entity_id=induction.id, action="resolve_effectivity", after=induction.validation_json["applicability"])
    return snapshot


def approve_induction(db: Session, induction: models.AircraftInduction, actor: User) -> models.AircraftInduction:
    if induction.status != "EFFECTIVITY_RESOLVED":
        raise _conflict("Effectivity must be resolved before induction approval", "EFFECTIVITY_REQUIRED")
    unresolved = [row.id for dataset in induction.datasets for row in dataset.rows if row.status in {"INVALID", "MAPPING_REQUIRED"} and row.decision != "REJECT"]
    if unresolved:
        raise HTTPException(status_code=422, detail={"code": "UNRESOLVED_ROWS", "row_ids": unresolved[:100]})
    induction.status = "APPROVED"
    induction.current_step = "ACTIVATE"
    induction.approved_by_user_id = actor.id
    induction.approved_at = utcnow()
    _audit(db, amo_id=induction.amo_id, actor=actor, entity_type="AircraftInduction", entity_id=induction.id, action="approve")
    return induction


def _latest_snapshot(db: Session, induction: models.AircraftInduction) -> models.AircraftApplicabilitySnapshot:
    snapshot = db.query(models.AircraftApplicabilitySnapshot).filter(models.AircraftApplicabilitySnapshot.induction_id == induction.id).order_by(models.AircraftApplicabilitySnapshot.created_at.desc()).first()
    if not snapshot:
        raise HTTPException(status_code=422, detail="No applicability snapshot exists for this induction")
    return snapshot


def _date_value(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _ensure_aircraft_master(db: Session, induction: models.AircraftInduction, context: dict[str, Any]) -> fleet_models.Aircraft:
    existing = db.query(fleet_models.Aircraft).filter(
        fleet_models.Aircraft.amo_id == induction.amo_id,
        or_(fleet_models.Aircraft.serial_number == induction.serial_number, fleet_models.Aircraft.registration == induction.registration),
    ).first()
    if existing:
        raise _conflict("Aircraft already exists. Use a controlled re-baseline workflow rather than re-induction.", "AIRCRAFT_ALREADY_EXISTS")
    variant = db.get(models.AircraftVariant, induction.variant_id)
    aircraft_type = variant.aircraft_type if variant else None
    family = aircraft_type.family if aircraft_type else None
    master_rows = _accepted_rows(induction, "AIRCRAFT_MASTER")
    master = master_rows[0] if master_rows else {}
    row = fleet_models.Aircraft(
        amo_id=induction.amo_id,
        serial_number=induction.serial_number,
        registration=induction.registration,
        aircraft_model_code=variant.model_code if variant else None,
        template=variant.variant_code if variant else None,
        make=family.manufacturer if family else master.get("make"),
        model=variant.model_code if variant else master.get("model"),
        operator_code=master.get("operator_code"),
        supplier_code=master.get("supplier_code"),
        company_name=master.get("company_name"),
        internal_aircraft_identifier=master.get("internal_aircraft_identifier"),
        home_base=master.get("home_base"),
        owner=master.get("owner"),
        status="OPEN",
        is_active=True,
        verification_status="VERIFIED",
        total_hours=0,
        total_cycles=0,
    )
    db.add(row)
    db.flush()
    return row


def _create_components(db: Session, induction: models.AircraftInduction) -> list[fleet_models.AircraftComponent]:
    created: list[fleet_models.AircraftComponent] = []
    seen_positions: set[str] = set()
    for source in _accepted_rows(induction, "CONFIGURATION") + _accepted_rows(induction, "COMPONENTS"):
        position = str(source.get("position") or "").strip().upper()
        if not position or position in seen_positions:
            continue
        seen_positions.add(position)
        row = fleet_models.AircraftComponent(
            amo_id=induction.amo_id,
            aircraft_serial_number=induction.serial_number,
            position=position,
            ata=source.get("ata") or source.get("ata_chapter"),
            part_number=source.get("part_number"),
            serial_number=source.get("serial_number"),
            description=source.get("description"),
            installed_date=_date_value(source.get("installed_date")),
            installed_hours=_parse_numeric(source.get("installed_hours")),
            installed_cycles=_parse_numeric(source.get("installed_cycles")),
            current_hours=_parse_numeric(source.get("current_hours")),
            current_cycles=_parse_numeric(source.get("current_cycles")),
            manufacturer_code=source.get("manufacturer_code"),
            operator_code=source.get("operator_code"),
            notes=source.get("notes"),
            is_installed=True,
            verification_status="VERIFIED",
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def _create_counter_opening(db: Session, induction: models.AircraftInduction, actor: User, counters: list[schemas.CounterBaselineCreate]) -> fleet_models.AircraftUsage | None:
    values = {item.counter_code.strip().upper(): item for item in counters}
    if not values:
        utilisation_rows = _accepted_rows(induction, "UTILISATION")
        if utilisation_rows:
            latest = utilisation_rows[-1]
            values = {
                "AIRFRAME_HOURS": schemas.CounterBaselineCreate(counter_code="AIRFRAME_HOURS", unit="H", value=Decimal(str(latest.get("total_hours") or latest.get("ttaf_after") or 0)), effective_date=_date_value(latest.get("date"))),
                "AIRFRAME_CYCLES": schemas.CounterBaselineCreate(counter_code="AIRFRAME_CYCLES", unit="C", value=Decimal(str(latest.get("total_cycles") or latest.get("tca_after") or 0)), effective_date=_date_value(latest.get("date"))),
            }
    hours = values.get("AIRFRAME_HOURS")
    cycles = values.get("AIRFRAME_CYCLES")
    if not hours and not cycles:
        return None
    effective_date = (hours.effective_date if hours else None) or (cycles.effective_date if cycles else None) or date.today()
    techlog = f"INDUCTION-{induction.induction_ref}"[:64]
    usage = fleet_models.AircraftUsage(
        amo_id=induction.amo_id,
        aircraft_serial_number=induction.serial_number,
        date=effective_date,
        techlog_no=techlog,
        station=None,
        block_hours=0,
        cycles=0,
        ttaf_after=float(hours.value) if hours else 0,
        tca_after=float(cycles.value) if cycles else 0,
        remarks="Controlled opening balance from universal aircraft induction",
        verification_status="VERIFIED",
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.add(usage)
    aircraft = db.get(fleet_models.Aircraft, induction.serial_number)
    if aircraft:
        aircraft.total_hours = usage.ttaf_after
        aircraft.total_cycles = usage.tca_after
        aircraft.last_log_date = effective_date
    for item in counters:
        db.add(models.InductionCounterBaseline(
            induction_id=induction.id,
            counter_code=item.counter_code.strip().upper(),
            unit=item.unit.strip().upper(),
            value=item.value,
            effective_date=item.effective_date,
            source_reference=item.source_reference,
        ))
    return usage


def _materialise_program(db: Session, induction: models.AircraftInduction, snapshot: models.AircraftApplicabilitySnapshot, actor: User) -> tuple[amp_revision_models.AmpProgramRevision, int]:
    tenant_revision = db.get(models.TenantMaintenanceProgramRevision, induction.program_revision_id)
    program = tenant_revision.program if tenant_revision else None
    if not tenant_revision or not program:
        raise HTTPException(status_code=422, detail="Tenant programme revision is unavailable")
    template_code = program.code[:50]
    amp_revision = db.query(amp_revision_models.AmpProgramRevision).filter(
        amp_revision_models.AmpProgramRevision.amo_id == induction.amo_id,
        amp_revision_models.AmpProgramRevision.template_code == template_code,
        amp_revision_models.AmpProgramRevision.revision_code == tenant_revision.revision_code[:32],
    ).first()
    if not amp_revision:
        amp_revision = amp_revision_models.AmpProgramRevision(
            amo_id=induction.amo_id,
            template_code=template_code,
            revision_code=tenant_revision.revision_code[:32],
            title=f"{program.title} {tenant_revision.revision_code}",
            status="APPROVED",
            effective_date=tenant_revision.effective_date,
            source_reference=tenant_revision.approval_reference,
            notes=f"Materialised from universal programme revision {tenant_revision.id}",
            approved_by_user_id=tenant_revision.approved_by_user_id,
            approved_at=tenant_revision.approved_at,
            created_by_user_id=actor.id,
        )
        db.add(amp_revision)
        db.flush()
    count = 0
    for requirement in snapshot.applicable_requirements_json:
        task_code = str(requirement.get("task_code") or requirement["requirement_key"])[:64]
        item = db.query(amp_models.AmpProgramItem).filter(
            amp_models.AmpProgramItem.template_code == template_code,
            amp_models.AmpProgramItem.task_code == task_code,
        ).first()
        interval = requirement.get("interval_json") or {}
        threshold = requirement.get("threshold_json") or {}
        if not item:
            item = amp_models.AmpProgramItem(
                template_code=template_code,
                ata_chapter=requirement.get("ata_chapter"),
                task_number=str(requirement.get("requirement_key"))[:64],
                task_code=task_code,
                title=str(requirement.get("title") or task_code)[:255],
                description=requirement.get("description"),
                is_mandatory=bool(requirement.get("mandatory", True)),
                interval_hours=_parse_numeric(interval.get("hours")),
                interval_cycles=_parse_numeric(interval.get("cycles")),
                interval_days=int(interval["days"]) if interval.get("days") is not None else None,
                threshold_hours=_parse_numeric(threshold.get("hours")),
                threshold_cycles=_parse_numeric(threshold.get("cycles")),
                threshold_days=int(threshold["days"]) if threshold.get("days") is not None else None,
                notes=json.dumps({"lineage": requirement.get("lineage"), "effectivity": requirement.get("effectivity_explanations")}, default=str),
                status=amp_models.ProgramItemStatusEnum.ACTIVE,
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            )
            db.add(item)
            db.flush()
        aircraft_item = db.query(amp_models.AmpAircraftProgramItem).filter(
            amp_models.AmpAircraftProgramItem.aircraft_serial_number == induction.serial_number,
            amp_models.AmpAircraftProgramItem.program_item_id == item.id,
            amp_models.AmpAircraftProgramItem.aircraft_component_id.is_(None),
        ).first()
        if not aircraft_item:
            aircraft_item = amp_models.AmpAircraftProgramItem(
                aircraft_serial_number=induction.serial_number,
                program_item_id=item.id,
                status=amp_models.AircraftProgramStatusEnum.PLANNED,
                notes=f"Applicability snapshot {snapshot.snapshot_hash}",
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            )
            db.add(aircraft_item)
            count += 1
    db.query(amp_revision_models.AmpAircraftBaseline).filter(
        amp_revision_models.AmpAircraftBaseline.amo_id == induction.amo_id,
        amp_revision_models.AmpAircraftBaseline.aircraft_serial_number == induction.serial_number,
        amp_revision_models.AmpAircraftBaseline.status == "ACTIVE",
    ).update({"status": "SUPERSEDED"}, synchronize_session=False)
    db.add(amp_revision_models.AmpAircraftBaseline(
        amo_id=induction.amo_id,
        aircraft_serial_number=induction.serial_number,
        revision_id=amp_revision.id,
        template_code=template_code,
        status="ACTIVE",
        applied_by_user_id=actor.id,
        notes=f"Universal induction binding {induction.id}; applicability {snapshot.snapshot_hash}",
    ))
    return amp_revision, count


def activate_induction(db: Session, induction: models.AircraftInduction, payload: schemas.ActivationRequest, actor: User) -> models.AircraftTemplateBinding:
    if induction.status != "APPROVED":
        raise _conflict("Induction must be approved before activation", "INDUCTION_APPROVAL_REQUIRED")
    snapshot = _latest_snapshot(db, induction)
    _ensure_aircraft_master(db, induction, snapshot.context_json)
    components = _create_components(db, induction)
    usage = _create_counter_opening(db, induction, actor, payload.counters)
    amp_revision, program_items = _materialise_program(db, induction, snapshot, actor)
    existing_bindings = db.query(models.AircraftTemplateBinding).filter(
        models.AircraftTemplateBinding.amo_id == induction.amo_id,
        models.AircraftTemplateBinding.aircraft_serial_number == induction.serial_number,
        models.AircraftTemplateBinding.status == "ACTIVE",
    ).all()
    for item in existing_bindings:
        item.status = "SUPERSEDED"
        item.superseded_at = utcnow()
    binding = models.AircraftTemplateBinding(
        amo_id=induction.amo_id,
        aircraft_serial_number=induction.serial_number,
        variant_id=induction.variant_id,
        template_revision_id=induction.template_revision_id,
        program_revision_id=induction.program_revision_id,
        applicability_snapshot_id=snapshot.id,
        activated_by_user_id=actor.id,
    )
    db.add(binding)
    db.flush()
    induction.status = "ACTIVE"
    induction.current_step = "COMPLETE"
    induction.activated_at = utcnow()
    induction.activation_manifest_json = {
        "approval_note": payload.approval_note,
        "aircraft_serial_number": induction.serial_number,
        "binding_id": binding.id,
        "template_revision_id": induction.template_revision_id,
        "program_revision_id": induction.program_revision_id,
        "applicability_snapshot_id": snapshot.id,
        "applicability_snapshot_hash": snapshot.snapshot_hash,
        "components_created": len(components),
        "opening_usage_id": usage.id if usage else None,
        "amp_revision_id": amp_revision.id,
        "aircraft_requirements_created": program_items,
        "activated_at": induction.activated_at.isoformat(),
    }
    _audit(db, amo_id=induction.amo_id, actor=actor, entity_type="AircraftInduction", entity_id=induction.id, action="activate", after=induction.activation_manifest_json)
    return binding


def workspace(db: Session, induction: models.AircraftInduction) -> schemas.InductionWorkspaceRead:
    snapshot = db.query(models.AircraftApplicabilitySnapshot).filter(models.AircraftApplicabilitySnapshot.induction_id == induction.id).order_by(models.AircraftApplicabilitySnapshot.created_at.desc()).first()
    binding = db.query(models.AircraftTemplateBinding).filter(models.AircraftTemplateBinding.amo_id == induction.amo_id, models.AircraftTemplateBinding.aircraft_serial_number == induction.serial_number, models.AircraftTemplateBinding.status == "ACTIVE").first()
    return schemas.InductionWorkspaceRead(
        induction=schemas.InductionRead.model_validate(induction),
        datasets=[schemas.DatasetRead.model_validate(item) for item in induction.datasets],
        rows_by_dataset={item.id: [schemas.RowRead.model_validate(row) for row in item.rows] for item in induction.datasets},
        applicability_snapshot=schemas.ApplicabilitySnapshotRead.model_validate(snapshot) if snapshot else None,
        binding=schemas.BindingRead.model_validate(binding) if binding else None,
    )
