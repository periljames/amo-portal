from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from amodb.apps.aircraft_architecture.aircraft_catalogue import models as catalogue_models
from amodb.apps.aircraft_architecture.content_packs import governance as content_governance
from amodb.apps.aircraft_architecture.content_packs import models as content_models

from . import models


MANDATORY_AUTHORITY_MARKERS = {"ALI", "CMR", "AWL", "AIRWORTHINESS LIMITATION", "LIFE LIMIT"}
BLOCKING_CURRENTNESS_STATES = {
    "NO_CURRENT_REVISION",
    "TEMPORARY_REVISION_REVIEW_REQUIRED",
    "CANDIDATE_REVIEW_REQUIRED",
    "SOURCE_CHANGE_DETECTED",
    "SOURCE_CHECK_REQUIRED",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _normalized(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def _exact_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("controlled interval values must use exact integers or decimal strings")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid controlled interval value") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError("controlled interval values must be finite and greater than zero")
    return result


def task_source_hash(task: content_models.AircraftContentPackTask) -> str:
    payload = {
        "id": task.id,
        "revision_id": task.revision_id,
        "task_code": task.task_code,
        "title": task.title,
        "description": task.description,
        "ata_chapter": task.ata_chapter,
        "programme_section": task.programme_section,
        "task_type": task.task_type,
        "intervals_json": task.intervals_json or {},
        "effectivity_expression_json": task.effectivity_expression_json or {},
        "source_requirements_json": task.source_requirements_json or [],
        "task_card_number": task.task_card_number,
        "task_card_configuration": task.task_card_configuration,
        "amm_reference": task.amm_reference,
        "source_reference": task.source_reference,
        "source_revision": task.source_revision,
        "source_checksum_sha256": task.source_checksum_sha256,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def derive_series(template: catalogue_models.AircraftTypeTemplate) -> tuple[str | None, str, str]:
    if template.series:
        return template.series.strip().upper(), "EXPLICIT", "Aircraft type catalogue series"

    text = " ".join(filter(None, [template.code, template.model, template.variant])).upper()
    if "Q400" in text:
        return "400", "DERIVED", "Q400 model identity"

    compact = re.sub(r"\s+", "", text)
    match = re.search(r"(?:DHC-?8|DH8)[-/]?([1-4]\d{2})", compact)
    if not match:
        match = re.search(r"(?:^|[^0-9])([1-4]\d{2})(?:[^0-9]|$)", text)
    if match:
        model_number = int(match.group(1))
        series = str((model_number // 100) * 100)
        if series in {"100", "200", "300", "400"}:
            return series, "DERIVED", f"Model {match.group(1)} maps to Dash 8 Series {series}"
    return None, "UNRESOLVED", "Aircraft type catalogue does not identify a series"


def _family_matches(pack: content_models.AircraftContentPack, template: catalogue_models.AircraftTypeTemplate) -> bool:
    manufacturer_ok = _normalized(pack.manufacturer) == _normalized(template.manufacturer)
    if not manufacturer_ok:
        return False
    candidates = {
        _normalized(template.family.code),
        _normalized(template.family.name),
        _normalized(template.model.split("-")[0]),
    }
    return _normalized(pack.family) in candidates or any(
        value and (value in _normalized(pack.family) or _normalized(pack.family) in value)
        for value in candidates
    )


def resolve_oem_baseline(
    db: Session,
    *,
    aircraft_type_revision_id: str,
) -> dict[str, Any]:
    type_revision = (
        db.query(catalogue_models.AircraftTypeTemplateRevision)
        .options(selectinload(catalogue_models.AircraftTypeTemplateRevision.template).selectinload(catalogue_models.AircraftTypeTemplate.family))
        .filter(catalogue_models.AircraftTypeTemplateRevision.id == aircraft_type_revision_id)
        .populate_existing()
        .first()
    )
    if not type_revision:
        raise HTTPException(status_code=404, detail="Aircraft type revision not found")
    if type_revision.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="Aircraft type revision must be published before programme resolution")

    series, confidence, reason = derive_series(type_revision.template)
    revision_rows = (
        db.query(content_models.AircraftContentPackRevision)
        .join(content_models.AircraftContentPack)
        .options(selectinload(content_models.AircraftContentPackRevision.sources))
        .filter(
            content_models.AircraftContentPack.status == "ACTIVE",
            content_models.AircraftContentPackRevision.status == "PUBLISHED",
        )
        .populate_existing()
        .all()
    )
    matches: list[dict[str, Any]] = []
    for revision in revision_rows:
        pack = revision.pack
        if not _family_matches(pack, type_revision.template):
            continue
        if series and _normalized(pack.series) != _normalized(series):
            continue
        if not any(source.publication_revision_id for source in revision.sources):
            continue
        matches.append(
            {
                "pack_id": pack.id,
                "pack_code": pack.code,
                "manufacturer": pack.manufacturer,
                "family": pack.family,
                "series": pack.series,
                "revision_id": revision.id,
                "revision_code": revision.revision_code,
                "content_hash": revision.content_hash,
            }
        )

    state = "RESOLVED" if len(matches) == 1 and series else "AMBIGUOUS" if len(matches) > 1 else "UNRESOLVED"
    if len(matches) == 1 and confidence == "DERIVED":
        state = "CONFIRM_DERIVED_SERIES"
    return {
        "aircraft_type_revision_id": type_revision.id,
        "template_id": type_revision.template.id,
        "template_code": type_revision.template.code,
        "model": type_revision.template.model,
        "variant": type_revision.template.variant,
        "series": series,
        "series_confidence": confidence,
        "series_reason": reason,
        "state": state,
        "candidates": matches,
    }


def _interval_groups(value: dict[str, Any]) -> list[dict[str, Any]]:
    if value.get("schema") != "MPD_INTERVAL_V1":
        raise ValueError("AMP strictness comparison requires MPD_INTERVAL_V1")
    groups = value.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("MPD interval groups are required")
    return groups


def _limit_key(row: dict[str, Any]) -> tuple[str, str]:
    counter = str(row.get("counter") or "").upper()
    custom = str(row.get("custom_counter") or "").strip().upper() if counter == "CUSTOM" else ""
    return counter, custom


def compare_interval_strictness(oem: dict[str, Any], amp: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    try:
        oem_groups = _interval_groups(oem)
        amp_groups = _interval_groups(amp)
    except ValueError as exc:
        return False, [str(exc)]

    def keyed(groups: Iterable[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        counts: dict[str, int] = {}
        result: dict[tuple[str, int], dict[str, Any]] = {}
        for group in groups:
            phase = str(group.get("phase") or "").upper()
            counts[phase] = counts.get(phase, 0) + 1
            result[(phase, counts[phase])] = group
        return result

    oem_by_key = keyed(oem_groups)
    amp_by_key = keyed(amp_groups)
    if set(oem_by_key) != set(amp_by_key):
        return False, ["AMP must preserve every OEM interval phase/group when tightening"]

    for key, oem_group in oem_by_key.items():
        amp_group = amp_by_key[key]
        oem_mode = str(oem_group.get("mode") or "SINGLE").upper()
        amp_mode = str(amp_group.get("mode") or "SINGLE").upper()
        if oem_mode != amp_mode:
            reasons.append(f"{key[0]} mode changed from {oem_mode} to {amp_mode}")
            continue
        if oem_mode == "OPPORTUNITY":
            if canonical_json(oem_group) != canonical_json(amp_group):
                reasons.append(f"{key[0]} opportunity control must be inherited unchanged")
            continue

        oem_limits = {_limit_key(row): row for row in oem_group.get("limits") or []}
        amp_limits = {_limit_key(row): row for row in amp_group.get("limits") or []}
        if set(oem_limits) != set(amp_limits):
            reasons.append(f"{key[0]} must preserve the OEM counter set")
            continue
        for limit_key, oem_limit in oem_limits.items():
            try:
                oem_value = _exact_decimal(oem_limit.get("value"))
                amp_value = _exact_decimal(amp_limits[limit_key].get("value"))
            except ValueError as exc:
                reasons.append(str(exc))
                continue
            if amp_value > oem_value:
                label = limit_key[1] or limit_key[0]
                reasons.append(f"{key[0]} {label} AMP limit {amp_value} exceeds OEM {oem_value}")
    return not reasons, reasons


def _is_mandatory(task: content_models.AircraftContentPackTask) -> bool:
    for requirement in task.source_requirements_json or []:
        text = canonical_json(requirement).upper()
        if any(marker in text for marker in MANDATORY_AUTHORITY_MARKERS):
            return True
    return False


def baseline_currentness_snapshot(
    db: Session,
    baseline: content_models.AircraftContentPackRevision,
) -> tuple[list[dict[str, Any]], str]:
    issues: list[dict[str, Any]] = []
    linked_base_ids = {source.publication_revision_id for source in baseline.sources if source.publication_revision_id}
    linked_tr_ids = {source.temporary_revision_id for source in baseline.sources if source.temporary_revision_id}
    if not linked_base_ids:
        return (
            [{
                "severity": "BLOCK",
                "code": "OEM_REGISTRY_LINEAGE_REQUIRED",
                "message": "Tenant AMP baselines must be linked to a controlled OEM publication revision",
            }],
            "UNCONTROLLED",
        )

    publication_states: list[str] = []
    checked_publications: set[str] = set()
    for revision_id in linked_base_ids:
        revision = db.get(content_models.AircraftOemPublicationRevision, revision_id)
        if not revision:
            issues.append({"severity": "BLOCK", "code": "OEM_SOURCE_MISSING", "message": "OEM source revision record is missing"})
            publication_states.append("NO_CURRENT_REVISION")
            continue
        if revision.status != "CURRENT":
            issues.append(
                {
                    "severity": "BLOCK",
                    "code": "OEM_BASELINE_SUPERSEDED",
                    "message": f"OEM publication revision {revision.revision_code} is {revision.status}; select the current OEM baseline",
                }
            )
        publication = revision.publication
        if publication.id not in checked_publications:
            checked_publications.add(publication.id)
            currentness = content_governance.governed_publication_currentness(db, publication=publication)
            publication_states.append(currentness.currentness_status)
            if currentness.currentness_status in BLOCKING_CURRENTNESS_STATES:
                issues.append(
                    {
                        "severity": "BLOCK",
                        "code": "OEM_CURRENTNESS_REVIEW_REQUIRED",
                        "message": (
                            f"OEM publication {publication.publication_code} is {currentness.currentness_status.replace('_', ' ').lower()}; "
                            "the source must be reviewed before an AMP revision can be published"
                        ),
                    }
                )
            elif currentness.currentness_status == "TEMPORARY_REVISION_ACTIVE":
                issues.append(
                    {
                        "severity": "INFO",
                        "code": "OEM_ACTIVE_TR_INCLUDED",
                        "message": f"OEM publication {publication.publication_code} has active Temporary Revision control; all active TRs must remain represented in the baseline",
                    }
                )

        active_trs = (
            db.query(content_models.AircraftOemTemporaryRevision)
            .filter(
                content_models.AircraftOemTemporaryRevision.publication_revision_id == revision.id,
                content_models.AircraftOemTemporaryRevision.status == "ACTIVE",
            )
            .all()
        )
        missing = [tr for tr in active_trs if tr.id not in linked_tr_ids]
        for tr in missing:
            issues.append(
                {
                    "severity": "BLOCK",
                    "code": "ACTIVE_TR_NOT_IN_BASELINE",
                    "message": f"Active OEM Temporary Revision {tr.temporary_revision_code} is not incorporated in this baseline",
                }
            )

    if any(state in BLOCKING_CURRENTNESS_STATES for state in publication_states):
        snapshot = "REVIEW_REQUIRED"
    elif "TEMPORARY_REVISION_ACTIVE" in publication_states:
        snapshot = "TEMPORARY_REVISION_ACTIVE"
    else:
        snapshot = "CURRENT"
    return issues, snapshot


def baseline_currentness_issues(
    db: Session,
    baseline: content_models.AircraftContentPackRevision,
) -> list[dict[str, Any]]:
    return baseline_currentness_snapshot(db, baseline)[0]


def validate_revision(
    db: Session,
    revision: models.TenantProgrammeRevision,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    baseline = db.get(content_models.AircraftContentPackRevision, revision.base_content_pack_revision_id) if revision.base_content_pack_revision_id else None
    if not baseline or baseline.status != "PUBLISHED":
        return {
            "status": "BLOCKED",
            "blocking_count": 1,
            "warning_count": 0,
            "issues": [{"severity": "BLOCK", "code": "OEM_BASELINE_REQUIRED", "message": "A published OEM baseline revision is required"}],
            "summary": {},
            "baseline": baseline,
        }

    currentness_issues, currentness_snapshot = baseline_currentness_snapshot(db, baseline)
    issues.extend(currentness_issues)
    oem_tasks = {task.id: task for task in baseline.tasks}
    tenant_by_source: dict[str, list[models.TenantProgrammeTask]] = {}
    additions = 0
    tightened = 0
    inherited = 0

    for task in revision.tasks:
        if task.decision == "LEGACY":
            issues.append({"severity": "BLOCK", "code": "LEGACY_UNMAPPED", "task_code": task.task_code, "message": "Legacy task must be reconciled to OEM or explicitly re-entered as ADD"})
            continue
        if task.decision == "ADD":
            additions += 1
            if task.source_content_task_id:
                issues.append({"severity": "BLOCK", "code": "ADD_HAS_OEM_SOURCE", "task_code": task.task_code, "message": "Operator-added AMP task must not masquerade as an OEM task"})
            if not (task.justification or "").strip():
                issues.append({"severity": "BLOCK", "code": "ADD_JUSTIFICATION_REQUIRED", "task_code": task.task_code, "message": "Operator-added AMP task requires a controlled justification"})
            continue
        if not task.source_content_task_id or task.source_content_task_id not in oem_tasks:
            issues.append({"severity": "BLOCK", "code": "OEM_TASK_LINK_INVALID", "task_code": task.task_code, "message": "Inherited/tightened AMP task must reference a task from the selected OEM baseline"})
            continue
        tenant_by_source.setdefault(task.source_content_task_id, []).append(task)
        oem = oem_tasks[task.source_content_task_id]
        expected_hash = task_source_hash(oem)
        if task.source_task_hash != expected_hash:
            issues.append({"severity": "BLOCK", "code": "OEM_TASK_CHANGED", "task_code": task.task_code, "message": "OEM task content changed after the AMP decision; reassessment is required"})
        if canonical_json(task.effectivity_expression_json or {}) != canonical_json(oem.effectivity_expression_json or {}):
            issues.append({"severity": "BLOCK", "code": "EFFECTIVITY_RELAXATION_NOT_ALLOWED", "task_code": task.task_code, "message": "AMP configuration may not broaden/narrow OEM applicability; effectivity is controlled by the OEM baseline"})
        if task.decision == "INHERIT":
            inherited += 1
            if canonical_json(task.intervals_json or {}) != canonical_json(oem.intervals_json or {}):
                issues.append({"severity": "BLOCK", "code": "INHERIT_MUST_MATCH_OEM", "task_code": task.task_code, "message": "INHERIT decision must use the OEM interval unchanged"})
        elif task.decision == "TIGHTEN":
            tightened += 1
            if not (task.justification or "").strip():
                issues.append({"severity": "BLOCK", "code": "TIGHTEN_JUSTIFICATION_REQUIRED", "task_code": task.task_code, "message": "A more restrictive AMP interval requires a controlled justification"})
            okay, reasons = compare_interval_strictness(oem.intervals_json or {}, task.intervals_json or {})
            if not okay:
                for reason in reasons:
                    issues.append({"severity": "BLOCK", "code": "AMP_EXCEEDS_OEM_LIMIT", "task_code": task.task_code, "message": reason})
            elif canonical_json(task.intervals_json or {}) != canonical_json(oem.intervals_json or {}):
                issues.append({"severity": "INFO", "code": "AMP_MORE_RESTRICTIVE", "task_code": task.task_code, "message": "Tenant AMP is more restrictive than the OEM baseline"})
        if _is_mandatory(oem) and task.decision not in {"INHERIT", "TIGHTEN"}:
            issues.append({"severity": "BLOCK", "code": "MANDATORY_REQUIREMENT", "task_code": task.task_code, "message": "Mandatory OEM requirement must be retained"})

    for source_id, oem in oem_tasks.items():
        linked = tenant_by_source.get(source_id, [])
        if not linked:
            issues.append({"severity": "BLOCK", "code": "OEM_TASK_MISSING", "task_code": oem.task_code, "message": "Applicable OEM baseline task is missing from the AMP draft"})
        elif len(linked) > 1:
            issues.append({"severity": "BLOCK", "code": "OEM_TASK_DUPLICATED", "task_code": oem.task_code, "message": "OEM task is represented more than once in the AMP draft"})

    blocking = sum(1 for issue in issues if issue["severity"] == "BLOCK")
    warnings = sum(1 for issue in issues if issue["severity"] == "WARN")
    state = "BLOCKED" if blocking else "WARN" if warnings else "PASS"
    return {
        "status": state,
        "blocking_count": blocking,
        "warning_count": warnings,
        "issues": issues,
        "summary": {
            "oem_task_count": len(oem_tasks),
            "inherited_count": inherited,
            "tightened_count": tightened,
            "operator_added_count": additions,
            "oem_currentness_at_validation": currentness_snapshot,
        },
        "baseline": baseline,
    }


def ensure_revision_publishable(db: Session, revision: models.TenantProgrammeRevision) -> dict[str, Any]:
    result = validate_revision(db, revision)
    if result["blocking_count"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "AMP revision has blocking OEM compliance issues",
                "validation": {key: value for key, value in result.items() if key != "baseline"},
            },
        )
    return result
