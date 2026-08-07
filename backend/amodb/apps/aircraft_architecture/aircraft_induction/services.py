from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models

from ..aircraft_catalogue import models as catalogue_models
from ..daily_utilisation import models as daily_models
from ..effectivity.evaluator import evaluate_expression
from ..tenant_programmes import models as programme_models
from . import models, schemas


ALLOWED_ROLES = {
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.PLANNING_ENGINEER,
    account_models.AccountRole.QUALITY_MANAGER,
}
CONTROLLED_COMPONENT_ROLES = {"ENGINE", "PROPELLER", "APU", "OTHER"}


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_key(
    reference: str,
    source_revision: str,
    checksum_sha256: str | None,
) -> tuple[str, str, str | None]:
    return (
        reference.strip(),
        source_revision.strip(),
        checksum_sha256.strip().lower() if checksum_sha256 else None,
    )


def _controlled_source_sort_key(source: Any) -> tuple[str, str, str, str, str, str]:
    return (
        str(source.reference or "").strip(),
        str(source.source_revision or "").strip(),
        str(source.checksum_sha256 or "").strip().lower(),
        str(source.source_type or "").strip(),
        str(source.authority or "").strip(),
        str(source.id),
    )


def require_human_induction_authority(user: account_models.User) -> str:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Active user account is required")
    if user.is_system_account:
        raise HTTPException(status_code=403, detail="System accounts cannot induct aircraft")
    amo_id = getattr(user, "amo_id", None)
    if not amo_id:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    if not (
        user.is_superuser
        or user.is_amo_admin
        or user.role in ALLOWED_ROLES
    ):
        raise HTTPException(status_code=403, detail="Aircraft induction authority is required")
    return str(amo_id)


def _request_payload(payload: schemas.AircraftInductionCreate) -> dict[str, Any]:
    return payload.model_dump(mode="json")


def _lock_idempotency_key(
    db: Session,
    *,
    amo_id: str,
    idempotency_key: str,
) -> None:
    """Serialize identical induction requests for the duration of the transaction."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"aircraft-induction:{amo_id}:{idempotency_key}"},
    )


def _load_type_revision(
    db: Session,
    revision_id: str,
) -> catalogue_models.AircraftTypeTemplateRevision:
    revision = (
        db.query(catalogue_models.AircraftTypeTemplateRevision)
        .filter(catalogue_models.AircraftTypeTemplateRevision.id == revision_id)
        .with_for_update(of=catalogue_models.AircraftTypeTemplateRevision)
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Aircraft type revision not found")
    if revision.status != "PUBLISHED" or not revision.content_hash:
        raise HTTPException(status_code=409, detail="Aircraft type revision must be published")
    if not revision.sources:
        raise HTTPException(status_code=409, detail="Aircraft type revision has no controlled source")
    return revision


def _load_programme_revision(
    db: Session,
    *,
    revision_id: str,
    amo_id: str,
    type_revision_id: str,
) -> programme_models.TenantProgrammeRevision:
    revision = (
        db.query(programme_models.TenantProgrammeRevision)
        .join(programme_models.TenantMaintenanceProgramme)
        .filter(
            programme_models.TenantProgrammeRevision.id == revision_id,
            programme_models.TenantMaintenanceProgramme.amo_id == amo_id,
        )
        .with_for_update(of=programme_models.TenantProgrammeRevision)
        .first()
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Tenant programme revision not found")
    if revision.status != "PUBLISHED" or not revision.content_hash:
        raise HTTPException(status_code=409, detail="Tenant programme revision must be published")
    if revision.aircraft_type_revision_id != type_revision_id:
        raise HTTPException(
            status_code=409,
            detail="Programme revision is not approved for the selected aircraft type revision",
        )
    return revision


def _configuration_lookup(
    revision: catalogue_models.AircraftTypeTemplateRevision,
) -> tuple[dict[str, catalogue_models.AircraftTypePosition], dict[str, catalogue_models.AircraftTypeComponentDefinition]]:
    positions = {row.code: row for row in revision.positions}
    definitions = {row.definition_code: row for row in revision.component_definitions}
    if len(positions) != len(revision.positions):
        raise HTTPException(status_code=409, detail="Aircraft type revision contains duplicate positions")
    if len(definitions) != len(revision.component_definitions):
        raise HTTPException(status_code=409, detail="Aircraft type revision contains duplicate component definitions")
    return positions, definitions


def _component_role(
    definition: catalogue_models.AircraftTypeComponentDefinition,
) -> str:
    metadata = definition.metadata_json or {}
    raw = metadata.get("utilisation_role")
    role = str(raw or "OTHER").strip().upper()
    if role not in CONTROLLED_COMPONENT_ROLES:
        raise HTTPException(
            status_code=409,
            detail=f"Unsupported controlled utilisation role on {definition.definition_code}",
        )
    return role


def _validate_components(
    payload: schemas.AircraftInductionCreate,
    revision: catalogue_models.AircraftTypeTemplateRevision,
) -> list[tuple[schemas.ComponentInductionInput, catalogue_models.AircraftTypeComponentDefinition, str]]:
    positions, definitions = _configuration_lookup(revision)
    approved_sources = {
        _source_key(source.reference, source.source_revision, source.checksum_sha256)
        for source in revision.sources
    }
    seen_positions: set[str] = set()
    resolved = []
    for item in payload.components:
        if item.position_code in seen_positions:
            raise HTTPException(status_code=422, detail=f"Duplicate component position: {item.position_code}")
        seen_positions.add(item.position_code)
        position = positions.get(item.position_code)
        definition = definitions.get(item.definition_code)
        if not position:
            raise HTTPException(status_code=422, detail=f"Unknown configuration position: {item.position_code}")
        if not definition or definition.position_code != item.position_code:
            raise HTTPException(
                status_code=422,
                detail=f"Component definition {item.definition_code} is not approved for {item.position_code}",
            )
        accepted = [str(value).strip().upper() for value in (definition.accepted_part_numbers_json or [])]
        if accepted and (not item.part_number or item.part_number.strip().upper() not in accepted):
            raise HTTPException(
                status_code=422,
                detail=f"Part number is not approved by definition {item.definition_code}",
            )
        if _source_key(
            item.source_reference,
            item.source_revision,
            item.source_checksum_sha256,
        ) not in approved_sources:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Component {item.definition_code} source does not exactly match "
                    "a controlled source on the published type revision"
                ),
            )
        resolved.append((item, definition, _component_role(definition)))
    required_positions = {row.code for row in revision.positions if row.required}
    missing = sorted(required_positions - seen_positions)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Required configuration positions are missing: {', '.join(missing)}",
        )
    return resolved


def _applicability_results(
    programme: programme_models.TenantProgrammeRevision,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for task in sorted(programme.tasks, key=lambda row: row.task_code):
        expression = task.effectivity_expression_json or {}
        if expression:
            evaluated = evaluate_expression(expression, context)
            if evaluated.unresolved_paths:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Task {task.task_code} effectivity is unresolved: "
                        + ", ".join(evaluated.unresolved_paths)
                    ),
                )
            result = evaluated.to_dict()
        else:
            result = {
                "applicable": True,
                "reasons": ["No restrictive effectivity expression"],
                "trace": [],
                "unresolved_paths": [],
            }
        results.append(
            {
                "task_id": task.id,
                "task_code": task.task_code,
                "source_reference": task.source_reference,
                "intervals": task.intervals_json,
                "result": result,
            }
        )
    return results


def induct_aircraft(
    db: Session,
    *,
    payload: schemas.AircraftInductionCreate,
    user: account_models.User,
) -> models.AircraftInduction:
    amo_id = require_human_induction_authority(user)
    request_payload = _request_payload(payload)
    request_hash = _canonical_hash(request_payload)
    _lock_idempotency_key(
        db,
        amo_id=amo_id,
        idempotency_key=payload.idempotency_key,
    )

    existing = (
        db.query(models.AircraftInduction)
        .filter(
            models.AircraftInduction.amo_id == amo_id,
            models.AircraftInduction.idempotency_key == payload.idempotency_key,
        )
        .with_for_update(of=models.AircraftInduction)
        .first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for a different induction request",
            )
        return existing

    type_revision = _load_type_revision(db, payload.type_revision_id)
    programme_revision = _load_programme_revision(
        db,
        revision_id=payload.programme_revision_id,
        amo_id=amo_id,
        type_revision_id=type_revision.id,
    )
    component_rows = _validate_components(payload, type_revision)

    conflict = db.query(fleet_models.Aircraft.serial_number).filter(
        (fleet_models.Aircraft.serial_number == payload.aircraft_serial_number)
        | (fleet_models.Aircraft.registration == payload.registration)
    ).first()
    if conflict:
        raise HTTPException(status_code=409, detail="Aircraft serial number or registration already exists")

    context = dict(payload.effectivity_context)
    context.update(
        {
            "aircraft_serial_number": payload.aircraft_serial_number,
            "registration": payload.registration,
            "aircraft": {
                "serial_number": payload.aircraft_serial_number,
                "registration": payload.registration,
                "type_revision_id": type_revision.id,
                "model_code": payload.model_code,
            },
        }
    )
    task_results = _applicability_results(programme_revision, context)

    now = datetime.now(timezone.utc)
    aircraft = fleet_models.Aircraft(
        serial_number=payload.aircraft_serial_number,
        amo_id=amo_id,
        registration=payload.registration,
        aircraft_model_code=payload.model_code,
        template=type_revision.template.code,
        make=payload.manufacturer or type_revision.template.manufacturer,
        model=payload.model or type_revision.template.model,
        home_base=payload.home_base,
        operator_code=payload.operator_code,
        company_name=payload.company_name,
        total_hours=float(payload.initial_airframe_hours),
        total_cycles=float(payload.initial_airframe_cycles),
        status="OPEN",
        is_active=True,
        verification_status="VERIFIED_FROM_INDUCTION",
    )
    db.add(aircraft)
    db.flush()

    induction = models.AircraftInduction(
        amo_id=amo_id,
        aircraft_serial_number=aircraft.serial_number,
        registration=aircraft.registration,
        type_revision_id=type_revision.id,
        programme_revision_id=programme_revision.id,
        idempotency_key=payload.idempotency_key,
        request_hash=request_hash,
        created_by_user_id=user.id,
        completed_at=now,
    )
    db.add(induction)
    db.flush()

    installed_components: list[
        tuple[
            schemas.ComponentInductionInput,
            catalogue_models.AircraftTypeComponentDefinition,
            str,
            fleet_models.AircraftComponent,
            dict[str, str],
        ]
    ] = []
    for item, definition, role in sorted(
        component_rows,
        key=lambda row: row[0].position_code,
    ):
        component = fleet_models.AircraftComponent(
            amo_id=amo_id,
            aircraft_serial_number=aircraft.serial_number,
            position=item.position_code,
            part_number=item.part_number,
            serial_number=item.serial_number,
            description=definition.description,
            installed_hours=float(item.baseline_hours) if item.baseline_hours is not None else None,
            installed_cycles=item.baseline_cycles,
            current_hours=float(item.baseline_hours) if item.baseline_hours is not None else None,
            current_cycles=item.baseline_cycles,
            verification_status="VERIFIED_FROM_INDUCTION",
            is_installed=True,
        )
        db.add(component)
        db.flush()
        source_json = {
            "reference": item.source_reference,
            "revision": item.source_revision,
            "checksum_sha256": item.source_checksum_sha256,
        }
        installed_components.append((item, definition, role, component, source_json))

    configuration_payload = {
        "aircraft_serial_number": aircraft.serial_number,
        "registration": aircraft.registration,
        "type_revision_id": type_revision.id,
        "type_content_hash": type_revision.content_hash,
        "sources": [
            {
                "id": source.id,
                "source_type": source.source_type,
                "reference": source.reference,
                "source_revision": source.source_revision,
                "checksum_sha256": source.checksum_sha256,
                "authority": source.authority,
            }
            for source in sorted(
                type_revision.sources,
                key=_controlled_source_sort_key,
            )
        ],
        "components": [
            {
                "position_code": item.position_code,
                "definition_id": definition.id,
                "definition_code": definition.definition_code,
                "component_id": component.id,
                "part_number": item.part_number,
                "serial_number": item.serial_number,
                "baseline_hours": str(item.baseline_hours) if item.baseline_hours is not None else None,
                "baseline_cycles": item.baseline_cycles,
                "utilisation_role": role,
                "source": source_json,
            }
            for item, definition, role, component, source_json in installed_components
        ],
        "initial_airframe_hours": str(payload.initial_airframe_hours),
        "initial_airframe_cycles": payload.initial_airframe_cycles,
    }
    configuration_hash = _canonical_hash(configuration_payload)
    configuration = models.AircraftConfigurationSnapshot(
        induction_id=induction.id,
        amo_id=amo_id,
        aircraft_serial_number=aircraft.serial_number,
        type_revision_id=type_revision.id,
        snapshot_hash=configuration_hash,
        snapshot_json=configuration_payload,
    )
    db.add(configuration)
    db.flush()

    for item, definition, _role, component, source_json in installed_components:
        db.add(
            models.AircraftConfigurationSnapshotItem(
                snapshot_id=configuration.id,
                position_code=item.position_code,
                definition_id=definition.id,
                aircraft_component_id=component.id,
                part_number=item.part_number,
                serial_number=item.serial_number,
                baseline_hours=item.baseline_hours,
                baseline_cycles=item.baseline_cycles,
                source_json=source_json,
            )
        )

    db.add(
        daily_models.AircraftExactUtilisationState(
            amo_id=amo_id,
            aircraft_serial_number=aircraft.serial_number,
            total_hours=payload.initial_airframe_hours,
            total_cycles=payload.initial_airframe_cycles,
            approved_source_reference="AIRCRAFT_INDUCTION",
            approved_by_user_id=user.id,
        )
    )
    for item, definition, role, component, _source_json in installed_components:
        db.add(
            models.AircraftComponentUtilisationRole(
                amo_id=amo_id,
                aircraft_component_id=component.id,
                role=role,
                assignment_source="TYPE_DEFINITION",
                source_definition_id=definition.id,
                source_reference=item.source_reference,
                assigned_by_user_id=user.id,
            )
        )
        db.add(
            daily_models.ComponentExactUtilisationState(
                amo_id=amo_id,
                aircraft_component_id=component.id,
                total_hours=item.baseline_hours,
                total_cycles=item.baseline_cycles,
                approved_source_reference=item.source_reference,
                approved_by_user_id=user.id,
            )
        )

    applicability_payload = {
        "programme_revision_id": programme_revision.id,
        "programme_content_hash": programme_revision.content_hash,
        "context": context,
        "task_results": task_results,
    }
    applicability = models.AircraftApplicabilitySnapshot(
        induction_id=induction.id,
        amo_id=amo_id,
        aircraft_serial_number=aircraft.serial_number,
        programme_revision_id=programme_revision.id,
        snapshot_hash=_canonical_hash(applicability_payload),
        context_json=context,
        task_results_json=task_results,
    )
    db.add(applicability)
    db.flush()

    lineage_payload = {
        "aircraft_serial_number": aircraft.serial_number,
        "type_revision_id": type_revision.id,
        "programme_revision_id": programme_revision.id,
        "configuration_snapshot_id": configuration.id,
        "configuration_snapshot_hash": configuration.snapshot_hash,
        "applicability_snapshot_id": applicability.id,
        "applicability_snapshot_hash": applicability.snapshot_hash,
        "type_content_hash": type_revision.content_hash,
        "programme_content_hash": programme_revision.content_hash,
    }
    lineage = models.AircraftEngineeringLineage(
        induction_id=induction.id,
        amo_id=amo_id,
        aircraft_serial_number=aircraft.serial_number,
        type_revision_id=type_revision.id,
        programme_revision_id=programme_revision.id,
        configuration_snapshot_id=configuration.id,
        applicability_snapshot_id=applicability.id,
        type_content_hash=type_revision.content_hash,
        programme_content_hash=programme_revision.content_hash,
        lineage_hash=_canonical_hash(lineage_payload),
        created_by_user_id=user.id,
    )
    db.add(lineage)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = db.query(models.AircraftInduction).filter(
            models.AircraftInduction.amo_id == amo_id,
            models.AircraftInduction.idempotency_key == payload.idempotency_key,
        ).first()
        if duplicate and duplicate.request_hash == request_hash:
            return duplicate
        raise HTTPException(status_code=409, detail="Aircraft induction conflicts with existing data") from exc

    db.refresh(induction)
    return induction
