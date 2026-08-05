from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import selectinload

from amodb.apps.fleet import models as fleet_models
from amodb.apps.maintenance_program import models as amp_models
from amodb.apps.maintenance_program import revision_models as amp_revision_models

from . import models, services as base
from .effectivity import evaluate_effectivity, validate_expression
from .services import *  # noqa: F401,F403


_base_create_counter_opening = base._create_counter_opening
_base_resolve_applicability = base.resolve_applicability
_base_publish_revision = base.publish_revision
_base_create_tenant_program_revision = base.create_tenant_program_revision


def publish_revision(db, revision_id, payload, actor):
    revision = (
        db.query(models.AircraftTypeTemplateRevision)
        .options(selectinload(models.AircraftTypeTemplateRevision.configuration_nodes))
        .filter(models.AircraftTypeTemplateRevision.id == revision_id)
        .first()
    )
    if revision:
        errors: list[str] = []
        for node in revision.configuration_nodes:
            errors.extend([f"configuration {node.node_key}: {item}" for item in validate_expression(node.effectivity_json)])
        if errors:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION_EFFECTIVITY", "errors": errors})
    return _base_publish_revision(db, revision_id, payload, actor)


def create_tenant_program_revision(db, program_id, payload, actor):
    base_revision = db.get(models.AircraftTypeTemplateRevision, payload.base_template_revision_id)
    if not base_revision or base_revision.status != "PUBLISHED":
        raise HTTPException(status_code=422, detail="New tenant programme revisions must be based on the currently published aircraft-type revision")
    return _base_create_tenant_program_revision(db, program_id, payload, actor)


def _configuration_blockers(revision, context: dict[str, Any]) -> list[str]:
    components = context.get("configuration", {}).get("components", []) or []
    blockers: list[str] = []
    for node in revision.configuration_nodes:
        result = evaluate_effectivity(node.effectivity_json, context)
        if not result.applicable:
            continue
        matches = []
        for component in components:
            position = str(component.get("position") or "").strip().upper()
            expected_position = str(node.position_code or "").strip().upper()
            if expected_position and position != expected_position:
                continue
            allowed = node.allowable_parts_json or []
            part_number = str(component.get("part_number") or "").strip().upper()
            if allowed:
                allowed_numbers = {
                    str(item.get("part_number") if isinstance(item, dict) else item).strip().upper()
                    for item in allowed
                }
                if part_number and part_number not in allowed_numbers:
                    blockers.append(
                        f"{node.node_key}: installed part {part_number} at {position or 'unresolved position'} is not in the allowable-part set"
                    )
                    continue
            matches.append(component)
        if len(matches) < int(node.minimum_quantity or 0):
            blockers.append(
                f"{node.node_key}: requires at least {node.minimum_quantity} matching installed item(s); found {len(matches)}"
            )
        if node.maximum_quantity is not None and len(matches) > int(node.maximum_quantity):
            blockers.append(
                f"{node.node_key}: permits at most {node.maximum_quantity} matching installed item(s); found {len(matches)}"
            )
    return blockers


def resolve_applicability(db, induction, actor):
    snapshot = _base_resolve_applicability(db, induction, actor)
    revision = (
        db.query(models.AircraftTypeTemplateRevision)
        .options(selectinload(models.AircraftTypeTemplateRevision.configuration_nodes))
        .filter(models.AircraftTypeTemplateRevision.id == induction.template_revision_id)
        .first()
    )
    blockers = _configuration_blockers(revision, snapshot.context_json) if revision else ["Template revision is unavailable"]
    if blockers:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CONFIGURATION_NOT_CONFORMING",
                "message": "Actual aircraft configuration does not conform to the selected aircraft-type revision.",
                "blockers": blockers,
            },
        )
    induction.validation_json = {
        **(induction.validation_json or {}),
        "configuration_conformity": {"status": "PASS", "blockers": []},
    }
    return snapshot


def _create_counter_opening(db, induction, actor, counters):
    usage = _base_create_counter_opening(db, induction, actor, counters)
    if not usage:
        return None
    existing_codes = {
        row.counter_code
        for row in db.query(models.InductionCounterBaseline)
        .filter(models.InductionCounterBaseline.induction_id == induction.id)
        .all()
    }
    synthesized = []
    if "AIRFRAME_HOURS" not in existing_codes:
        synthesized.append(("AIRFRAME_HOURS", "H", Decimal(str(usage.ttaf_after or 0))))
    if "AIRFRAME_CYCLES" not in existing_codes:
        synthesized.append(("AIRFRAME_CYCLES", "C", Decimal(str(usage.tca_after or 0))))
    for code, unit, value in synthesized:
        db.add(models.InductionCounterBaseline(
            induction_id=induction.id,
            counter_code=code,
            unit=unit,
            value=value,
            effective_date=usage.date,
            source_reference=induction.source_reference,
        ))
    return usage


def _materialise_program(db, induction, snapshot, actor):
    tenant_revision = db.get(models.TenantMaintenanceProgramRevision, induction.program_revision_id)
    program = tenant_revision.program if tenant_revision else None
    if not tenant_revision or not program:
        raise HTTPException(status_code=422, detail="Tenant programme revision is unavailable")

    revision_suffix = tenant_revision.revision_code.strip().upper()
    template_code = f"{program.code}:{revision_suffix}"[:50]
    amp_revision = db.query(amp_revision_models.AmpProgramRevision).filter(
        amp_revision_models.AmpProgramRevision.amo_id == induction.amo_id,
        amp_revision_models.AmpProgramRevision.template_code == template_code,
        amp_revision_models.AmpProgramRevision.revision_code == revision_suffix[:32],
    ).first()
    if not amp_revision:
        amp_revision = amp_revision_models.AmpProgramRevision(
            amo_id=induction.amo_id,
            template_code=template_code,
            revision_code=revision_suffix[:32],
            title=f"{program.title} {revision_suffix}",
            status="APPROVED",
            effective_date=tenant_revision.effective_date,
            source_reference=tenant_revision.approval_reference,
            notes=f"Universal programme revision {tenant_revision.id}; base type revision {tenant_revision.base_template_revision_id}",
            approved_by_user_id=tenant_revision.approved_by_user_id,
            approved_at=tenant_revision.approved_at,
            created_by_user_id=actor.id,
        )
        db.add(amp_revision)
        db.flush()

    count = 0
    for requirement in snapshot.applicable_requirements_json:
        task_code = str(requirement.get("task_code") or requirement["requirement_key"])[:64]
        interval = requirement.get("interval_json") or {}
        threshold = requirement.get("threshold_json") or {}
        item = db.query(amp_models.AmpProgramItem).filter(
            amp_models.AmpProgramItem.template_code == template_code,
            amp_models.AmpProgramItem.task_code == task_code,
        ).first()
        if not item:
            item = amp_models.AmpProgramItem(
                template_code=template_code,
                ata_chapter=requirement.get("ata_chapter"),
                task_number=str(requirement.get("requirement_key"))[:64],
                task_code=task_code,
                title=str(requirement.get("title") or task_code)[:255],
                description=requirement.get("description"),
                is_mandatory=bool(requirement.get("mandatory", True)),
                interval_hours=base._parse_numeric(interval.get("hours")),
                interval_cycles=base._parse_numeric(interval.get("cycles")),
                interval_days=int(interval["days"]) if interval.get("days") is not None else None,
                threshold_hours=base._parse_numeric(threshold.get("hours")),
                threshold_cycles=base._parse_numeric(threshold.get("cycles")),
                threshold_days=int(threshold["days"]) if threshold.get("days") is not None else None,
                notes=json.dumps({
                    "type_template_revision_id": induction.template_revision_id,
                    "tenant_program_revision_id": induction.program_revision_id,
                    "applicability_snapshot_hash": snapshot.snapshot_hash,
                    "lineage": requirement.get("lineage"),
                    "effectivity": requirement.get("effectivity_explanations"),
                }, default=str),
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
            db.add(amp_models.AmpAircraftProgramItem(
                aircraft_serial_number=induction.serial_number,
                program_item_id=item.id,
                status=amp_models.AircraftProgramStatusEnum.PLANNED,
                notes=f"Applicability snapshot {snapshot.snapshot_hash}",
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
            ))
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
        notes=f"Universal induction {induction.id}; type revision {induction.template_revision_id}; applicability {snapshot.snapshot_hash}",
    ))
    return amp_revision, count


# Patch the base module so activate_induction, whose globals belong to that
# module, executes the hardened implementations.
base._create_counter_opening = _create_counter_opening
base._materialise_program = _materialise_program
base.resolve_applicability = resolve_applicability
