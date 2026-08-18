from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from . import governance_models as models
from . import governance_rules as rules
from . import models as legacy_models
from .permissions import tenant_id_for


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_row(db: Session, model, *, amo_id: str, row_id: str, label: str):
    row = db.query(model).filter(model.id == row_id, model.amo_id == amo_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} was not found in this tenant.")
    return row


def _dict(row) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def list_effective_rules(
    db: Session,
    *,
    amo_id: str,
    on_date: date,
    context: Mapping[str, object] | None = None,
    rule_code: str | None = None,
) -> tuple[list[models.TrainingGovernanceRule], list[dict[str, object]]]:
    query = db.query(models.TrainingGovernanceRule).filter(
        models.TrainingGovernanceRule.amo_id == amo_id,
        models.TrainingGovernanceRule.status == "ACTIVE",
    )
    if rule_code:
        query = query.filter(models.TrainingGovernanceRule.rule_code == rule_code)
    rows = query.order_by(models.TrainingGovernanceRule.rule_code, models.TrainingGovernanceRule.effective_from.desc()).all()
    effective = rules.effective_rules([_dict(row) for row in rows], on_date=on_date, context=context or {})
    effective_ids = {str(row["id"]) for row in effective}
    selected = [row for row in rows if str(row.id) in effective_ids]
    conflicts = rules.rule_conflicts(effective)
    return selected, conflicts


def persist_conflicts(
    db: Session,
    *,
    amo_id: str,
    conflicts: Iterable[Mapping[str, object]],
    context: Mapping[str, object] | None = None,
) -> None:
    for conflict in conflicts:
        rule_code = str(conflict.get("rule_code") or "")
        rule_ids = [str(value) for value in conflict.get("rule_ids", [])]
        existing = db.query(models.TrainingGovernanceConflict).filter(
            models.TrainingGovernanceConflict.amo_id == amo_id,
            models.TrainingGovernanceConflict.rule_code == rule_code,
            models.TrainingGovernanceConflict.status == "OPEN",
        ).first()
        if existing:
            existing.rule_ids = rule_ids
            existing.conflict_summary = str(conflict.get("message") or "Controlled rules conflict.")
            existing.affected_context = dict(context or {})
            continue
        db.add(
            models.TrainingGovernanceConflict(
                amo_id=amo_id,
                rule_code=rule_code,
                rule_ids=rule_ids,
                conflict_summary=str(conflict.get("message") or "Controlled rules conflict."),
                affected_context=dict(context or {}),
            )
        )


def technical_authorisation_readiness(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    privilege_type: str,
    on_date: date,
    course_id: str | None = None,
    aircraft: str | None = None,
    require_theory: bool = False,
    require_practical: bool = False,
    require_ojt: bool = False,
) -> dict[str, object]:
    authorisations = db.query(models.TrainingTechnicalAuthorisation).filter(
        models.TrainingTechnicalAuthorisation.amo_id == amo_id,
        models.TrainingTechnicalAuthorisation.user_id == user_id,
        models.TrainingTechnicalAuthorisation.privilege_type == privilege_type.upper(),
    ).order_by(models.TrainingTechnicalAuthorisation.expiry_date.desc()).all()
    if not authorisations:
        return {"eligible": False, "authorisation_id": None, "reasons": [f"No controlled {privilege_type.lower()} authorisation exists for this person."]}

    best: tuple[models.TrainingTechnicalAuthorisation, list[str]] | None = None
    for row in authorisations:
        # Dependency evidence is explicit on the authorisation.  Empty dependency
        # sets are valid; populated dependencies must carry a current=true result
        # from the canonical licence/training/observation verification workflow.
        dependencies = list(row.training_dependencies or [])
        licence = dict(row.licence_dependency or {})
        dependency_states = [bool(item.get("current")) for item in dependencies if isinstance(item, dict) and "current" in item]
        if licence and "current" in licence:
            dependency_states.append(bool(licence.get("current")))
        dependencies_satisfied = all(dependency_states) if dependency_states else True
        reasons = rules.technical_authorisation_reasons(
            _dict(row),
            on_date=on_date,
            privilege_type=privilege_type,
            course_id=course_id,
            aircraft=aircraft,
            require_theory=require_theory,
            require_practical=require_practical,
            require_ojt=require_ojt,
            dependencies_satisfied=dependencies_satisfied,
        )
        if not reasons:
            return {"eligible": True, "authorisation_id": str(row.id), "reasons": []}
        if best is None or len(reasons) < len(best[1]):
            best = (row, reasons)
    assert best is not None
    return {"eligible": False, "authorisation_id": str(best[0].id), "reasons": best[1]}


def course_revision_reconciliation(db: Session, *, amo_id: str, revision_id: str) -> dict[str, object]:
    revision = _tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
    modules = db.query(models.TrainingCourseModule).filter(
        models.TrainingCourseModule.amo_id == amo_id,
        models.TrainingCourseModule.course_revision_id == revision.id,
    ).order_by(models.TrainingCourseModule.sequence_no).all()
    return rules.course_revision_reconciliation(revision=_dict(revision), modules=[_dict(row) for row in modules])


def external_credit_check(
    db: Session,
    *,
    amo_id: str,
    provider_id: str,
    training_date: date,
    course_id: str | None,
    authority_id: str | None,
) -> dict[str, object]:
    provider = _tenant_row(db, models.TrainingProvider, amo_id=amo_id, row_id=provider_id, label="Training provider")
    reasons = rules.provider_credit_reasons(
        _dict(provider), training_date=training_date, course_id=course_id, authority_id=authority_id,
    )
    return {
        "accepted": not reasons,
        "provider_id": str(provider.id),
        "reasons": reasons,
        "action": "ACCEPT" if not reasons else "RESOLVE_BLOCKERS",
    }


def _check(code: str, label: str, satisfied: bool, message: str, *, severity: str = "BLOCK", target: str | None = None) -> dict[str, object]:
    return {
        "code": code,
        "label": label,
        "satisfied": satisfied,
        "severity": severity,
        "message": message,
        "action": None if satisfied else {"kind": "OPEN_WORKSPACE", "target": target or "CONTROL"},
    }


def evaluate_session_readiness(
    db: Session,
    *,
    amo_id: str,
    event_id: str,
    persist: bool = True,
) -> dict[str, object]:
    event = _tenant_row(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=event_id, label="Training session")
    envelope = db.query(models.TrainingSessionGovernance).filter(
        models.TrainingSessionGovernance.amo_id == amo_id,
        models.TrainingSessionGovernance.event_id == event.id,
    ).first()
    checks: list[dict[str, object]] = []
    if not envelope:
        result = rules.readiness_result([
            _check("SESSION_GOVERNANCE", "Governed session envelope", False, "The session has not been linked to an approved course revision, facility and technical-authorisation envelope.")
        ])
        result.update(event_id=str(event.id), evaluated_at=_utcnow())
        return result

    on_date = event.starts_on
    revision = _tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=envelope.course_revision_id, label="Course revision")
    revision_active = str(revision.status).upper() == "ACTIVE" and (revision.effective_from is None or revision.effective_from <= on_date) and (revision.effective_to is None or revision.effective_to >= on_date)
    checks.append(_check("COURSE_REVISION", "Approved course revision", revision_active, "Course revision is active for the session date." if revision_active else "The selected course revision is not active/effective for the session date.", target="PROGRAMMES"))

    reconciliation = course_revision_reconciliation(db, amo_id=amo_id, revision_id=str(revision.id))
    checks.append(_check("COURSE_HOURS", "Curriculum hour reconciliation", not reconciliation["blockers"], "Course module hours reconcile." if not reconciliation["blockers"] else " ".join(reconciliation["blockers"]), target="PROGRAMMES"))

    if revision.course_approval_id:
        approval = _tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=revision.course_approval_id, label="Course approval")
        approval_blockers = rules.approval_reasons(_dict(approval), on_date=on_date)
        checks.append(_check("COURSE_APPROVAL", "Course approval envelope", not approval_blockers, "Course approval is current." if not approval_blockers else " ".join(approval_blockers), target="CONTROL"))
    else:
        approval_required = bool((revision.completion_rules or {}).get("course_approval_required", False))
        checks.append(_check("COURSE_APPROVAL", "Course approval envelope", not approval_required, "No separate course approval is required by the controlled revision." if not approval_required else "A controlled course approval is required but is not linked.", target="CONTROL"))

    participant_count = int(db.query(func.count(legacy_models.TrainingEventParticipant.id)).filter(
        legacy_models.TrainingEventParticipant.amo_id == amo_id,
        legacy_models.TrainingEventParticipant.event_id == event.id,
    ).scalar() or 0)
    facility_required = bool((revision.facility_requirements or {}).get("approval_required", False))
    if envelope.facility_id:
        facility = _tenant_row(db, models.TrainingFacility, amo_id=amo_id, row_id=envelope.facility_id, label="Training facility")
        facility_blockers = rules.facility_reasons(
            _dict(facility), on_date=on_date, learners=participant_count, practical_learners=participant_count if revision.practical_hours else 0, approval_required=facility_required,
        )
        checks.append(_check("FACILITY", "Approved facility and capacity", not facility_blockers, "Facility is approved and within capacity." if not facility_blockers else " ".join(facility_blockers), target="CONTROL"))
    else:
        checks.append(_check("FACILITY", "Approved facility and capacity", not facility_required, "No controlled facility is required." if not facility_required else "The course requires an approved facility but none is assigned.", target="CONTROL"))

    required_materials = db.query(models.TrainingMaterialRevision).filter(
        models.TrainingMaterialRevision.amo_id == amo_id,
        models.TrainingMaterialRevision.course_revision_id == revision.id,
        models.TrainingMaterialRevision.required.is_(True),
    ).all()
    material_blockers: list[str] = []
    for material in required_materials:
        active = str(material.status).upper() == "ACTIVE"
        effective = (material.effective_from is None or material.effective_from <= on_date) and (material.effective_to is None or material.effective_to >= on_date)
        controlled = bool(material.dms_revision_id)
        if not (active and effective and controlled):
            material_blockers.append(f"{material.material_code} revision {material.revision_no} is not a current controlled material for the session date.")
    checks.append(_check("MATERIALS", "Current controlled materials", not material_blockers, "All required materials are current." if not material_blockers else " ".join(material_blockers), target="PROGRAMMES"))

    instructor_requirements = dict(revision.instructor_requirements or {})
    require_instructor = bool(instructor_requirements) or bool(envelope.instructor_authorisation_ids)
    instructor_blockers: list[str] = []
    if require_instructor and not envelope.instructor_authorisation_ids:
        instructor_blockers.append("No controlled instructor authorisation is assigned.")
    for auth_id in list(envelope.instructor_authorisation_ids or []):
        auth = _tenant_row(db, models.TrainingTechnicalAuthorisation, amo_id=amo_id, row_id=str(auth_id), label="Instructor authorisation")
        result = technical_authorisation_readiness(
            db,
            amo_id=amo_id,
            user_id=str(auth.user_id),
            privilege_type="INSTRUCTOR",
            on_date=on_date,
            course_id=str(revision.course_id),
            aircraft=instructor_requirements.get("aircraft"),
            require_theory=bool(revision.theory_hours),
            require_practical=bool(revision.practical_hours),
        )
        instructor_blockers.extend(result["reasons"])
    checks.append(_check("INSTRUCTOR", "Eligible instructor", not instructor_blockers, "Assigned instructor authorisations are current and in scope." if not instructor_blockers else " ".join(instructor_blockers), target="PEOPLE"))

    context = {"course_id": str(revision.course_id), "event_id": str(event.id), "delivery_methods": list(revision.delivery_methods or [])}
    effective_rule_rows, conflicts = list_effective_rules(db, amo_id=amo_id, on_date=on_date, context=context)
    if conflicts:
        persist_conflicts(db, amo_id=amo_id, conflicts=conflicts, context=context)
    checks.append(_check("CONTROLLED_RULES", "Controlled rule consistency", not conflicts, "Applicable controlled rules have no unresolved conflict." if not conflicts else "One or more current controlled sources conflict; human resolution is required before the session can start.", target="CONTROL"))

    # Preserve source attribution in the explainable snapshot even when no rule
    # produces a blocker.  Numeric/procedural rule evaluators consume value_json
    # by rule_code rather than global constants.
    applicable_rule_sources = [
        {
            "rule_code": row.rule_code,
            "severity": row.severity,
            "source_document_id": row.source_document_id,
            "source_revision_id": row.source_revision_id,
            "source_section": row.source_section,
            "source_paragraph": row.source_paragraph,
        }
        for row in effective_rule_rows
    ]

    result = rules.readiness_result(checks)
    evaluated_at = _utcnow()
    result.update(event_id=str(event.id), evaluated_at=evaluated_at, applicable_rules=applicable_rule_sources)
    if persist:
        envelope.readiness_status = result["status"]
        envelope.readiness_snapshot = {
            "status": result["status"], "checks": result["checks"], "applicable_rules": applicable_rule_sources,
        }
        envelope.readiness_evaluated_at = evaluated_at
    return result


def impact_preview(
    db: Session,
    *,
    actor: account_models.User,
    source_document_id: str,
    previous_revision_id: str | None,
    new_revision_id: str,
) -> models.TrainingImpactAssessment:
    amo_id = tenant_id_for(actor)
    references = db.query(models.TrainingCourseReference).filter(
        models.TrainingCourseReference.amo_id == amo_id,
        models.TrainingCourseReference.source_document_id == source_document_id,
    ).all()
    course_revision_ids = {str(row.course_revision_id) for row in references}
    question_revisions = db.query(models.TrainingQuestionRevision).filter(
        models.TrainingQuestionRevision.amo_id == amo_id,
        models.TrainingQuestionRevision.source_document_id == source_document_id,
    ).all()
    rule_rows = db.query(models.TrainingGovernanceRule).filter(
        models.TrainingGovernanceRule.amo_id == amo_id,
        models.TrainingGovernanceRule.source_document_id == source_document_id,
        models.TrainingGovernanceRule.status == "ACTIVE",
    ).all()
    materials = db.query(models.TrainingMaterialRevision).filter(
        models.TrainingMaterialRevision.amo_id == amo_id,
        models.TrainingMaterialRevision.dms_document_id == source_document_id,
    ).all()
    course_revision_ids.update(str(row.course_revision_id) for row in materials)

    scheduled_sessions = []
    if course_revision_ids:
        scheduled_sessions = db.query(models.TrainingSessionGovernance).filter(
            models.TrainingSessionGovernance.amo_id == amo_id,
            models.TrainingSessionGovernance.course_revision_id.in_(course_revision_ids),
            models.TrainingSessionGovernance.status.in_(["PLANNED", "READY"]),
        ).all()

    technical_auths = db.query(models.TrainingTechnicalAuthorisation).filter(
        models.TrainingTechnicalAuthorisation.amo_id == amo_id,
        models.TrainingTechnicalAuthorisation.status == "ACTIVE",
    ).all()
    affected_course_ids = {
        str(row.course_id)
        for row in db.query(models.TrainingCourseRevision).filter(
            models.TrainingCourseRevision.amo_id == amo_id,
            models.TrainingCourseRevision.id.in_(course_revision_ids or {"__none__"}),
        ).all()
    }
    affected_auths = [row for row in technical_auths if affected_course_ids.intersection({str(value) for value in row.course_ids or []})]

    summary = {
        "course_revisions": len(course_revision_ids),
        "question_revisions": len(question_revisions),
        "governance_rules": len(rule_rows),
        "materials": len(materials),
        "technical_authorisations": len(affected_auths),
        "scheduled_sessions": len(scheduled_sessions),
    }
    blockers = []
    if question_revisions:
        blockers.append("Referenced examination questions require human review before reuse with the new controlled revision.")
    if scheduled_sessions:
        blockers.append("Scheduled sessions reference affected controlled content and require readiness re-evaluation.")

    assessment = models.TrainingImpactAssessment(
        amo_id=amo_id,
        source_document_id=source_document_id,
        previous_revision_id=previous_revision_id,
        new_revision_id=new_revision_id,
        status="PREVIEW",
        summary_json=summary,
        blockers_json=blockers,
        created_by_user_id=str(actor.id),
    )
    db.add(assessment)
    db.flush()

    for revision_id in sorted(course_revision_ids):
        db.add(models.TrainingImpactItem(amo_id=amo_id, impact_assessment_id=assessment.id, entity_type="COURSE_REVISION", entity_id=revision_id, reason="Controlled source revision changed.", required_action="Review course content and activate an approved revision before delivery.", blocking=True))
    for row in question_revisions:
        db.add(models.TrainingImpactItem(amo_id=amo_id, impact_assessment_id=assessment.id, entity_type="QUESTION_REVISION", entity_id=str(row.id), reason="Question cites the changed controlled source.", required_action="Review, revise or retire through examination governance.", blocking=True))
    for row in affected_auths:
        db.add(models.TrainingImpactItem(amo_id=amo_id, impact_assessment_id=assessment.id, entity_type="TECHNICAL_AUTHORISATION", entity_id=str(row.id), reason="Authorisation scope includes an affected course.", required_action="Confirm continuing instructor/examiner/assessor competence and scope.", blocking=False))
    for row in scheduled_sessions:
        db.add(models.TrainingImpactItem(amo_id=amo_id, impact_assessment_id=assessment.id, entity_type="SESSION", entity_id=str(row.event_id), reason="Scheduled session uses an affected course revision.", required_action="Re-run session readiness after controlled content review.", blocking=True))
    return assessment


def learner_question_projection(revision: models.TrainingQuestionRevision) -> dict[str, object]:
    """Deliberately omit answer_key_json and explanation from learner APIs."""
    return {
        "question_revision_id": str(revision.id),
        "prompt": revision.prompt,
        "options": list(revision.options_json or []),
        "marks": revision.marks,
    }
