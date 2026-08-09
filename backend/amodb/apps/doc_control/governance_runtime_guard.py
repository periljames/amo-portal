from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from . import governance_models as gm
from . import governance_service as service
from . import knowledge_models as km


_LIMITS = {
    "revisions": 50,
    "responsibilities": 200,
    "relationships": 150,
    "detected_references": 150,
    "index_jobs": 50,
    "annotations": 250,
    "structure_children": 100,
    "assignment_users": 250,
    "assignment_departments": 100,
    "assignment_org_units": 250,
}


def _bounded(query, limit: int):
    rows = query.limit(limit + 1).all()
    return rows[:limit], len(rows) > limit


def _bound(limit: int, rows: list[Any], has_more: bool) -> dict[str, Any]:
    return {"limit": limit, "returned": len(rows), "has_more": has_more}


def _bounded_structure(db: Session, *, tenant_id: str, manual_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    row = db.query(km.DocumentationNode).filter(
        km.DocumentationNode.tenant_id == tenant_id,
        km.DocumentationNode.manual_id == manual_id,
    ).first()
    if not row:
        return None, _bound(_LIMITS["structure_children"], [], False)
    children, more = _bounded(
        db.query(km.DocumentationNode).filter(
            km.DocumentationNode.tenant_id == tenant_id,
            km.DocumentationNode.parent_id == row.id,
        ).order_by(km.DocumentationNode.order_index.asc()),
        _LIMITS["structure_children"],
    )
    parent = db.query(km.DocumentationNode).filter(km.DocumentationNode.id == row.parent_id).first() if row.parent_id else None
    return {
        "id": row.id,
        "parent_id": row.parent_id,
        "parent": ({"id": parent.id, "code": parent.code, "title": parent.title, "node_type": parent.node_type} if parent else None),
        "code": row.code,
        "title": row.title,
        "node_type": row.node_type,
        "path": row.path,
        "depth": row.depth,
        "order_index": row.order_index,
        "status": row.status,
        "provenance": dict(row.metadata_json or {}),
        "children": [
            {"id": child.id, "code": child.code, "title": child.title, "node_type": child.node_type, "status": child.status}
            for child in children
        ],
    }, _bound(_LIMITS["structure_children"], children, more)


def bounded_document_governance_payload(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    current_user: account_models.User,
) -> dict[str, Any]:
    profile = service.get_profile(db, tenant, manual.id)
    if not service.can_read_manual(current_user, profile):
        raise HTTPException(status_code=403, detail="Document access denied")
    target, target_kind = service.readable_revision(db, manual, current_user)
    bounds: dict[str, dict[str, Any]] = {}

    revisions, more = _bounded(
        db.query(manual_models.ManualRevision).filter(
            manual_models.ManualRevision.manual_id == manual.id,
        ).order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc()),
        _LIMITS["revisions"],
    )
    bounds["revisions"] = _bound(_LIMITS["revisions"], revisions, more)

    assignments, more = _bounded(
        db.query(gm.DocumentResponsibilityAssignment).filter(
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.manual_id == manual.id,
        ).order_by(gm.DocumentResponsibilityAssignment.responsibility_type.asc(), gm.DocumentResponsibilityAssignment.created_at.desc()),
        _LIMITS["responsibilities"],
    )
    bounds["responsibilities"] = _bound(_LIMITS["responsibilities"], assignments, more)
    users = service._user_labels(db, {row.assignee_user_id for row in assignments if row.assignee_user_id})
    departments = service._department_labels(db, {row.assignee_department_id for row in assignments if row.assignee_department_id})
    grouped = service.effective_assignments(assignments)

    relationships, more = _bounded(
        db.query(gm.DocumentGovernedRelationship).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            gm.DocumentGovernedRelationship.source_manual_id == manual.id,
        ).order_by(gm.DocumentGovernedRelationship.updated_at.desc()),
        _LIMITS["relationships"],
    )
    bounds["relationships"] = _bound(_LIMITS["relationships"], relationships, more)

    references, more = _bounded(
        db.query(km.DocumentationReference).filter(
            km.DocumentationReference.tenant_id == tenant.amo_id,
            km.DocumentationReference.source_manual_id == manual.id,
        ).order_by(km.DocumentationReference.updated_at.desc()),
        _LIMITS["detected_references"],
    )
    bounds["detected_references"] = _bound(_LIMITS["detected_references"], references, more)

    target_manual_ids = {row.target_manual_id for row in relationships if row.target_manual_id} | {row.target_manual_id for row in references if row.target_manual_id}
    manuals = {row.id: row for row in db.query(manual_models.Manual).filter(manual_models.Manual.id.in_(target_manual_ids or ["-"])).all()}

    index_jobs, more = _bounded(
        db.query(km.DocumentationIndexJob).filter(
            km.DocumentationIndexJob.tenant_id == tenant.amo_id,
            km.DocumentationIndexJob.manual_id == manual.id,
        ).order_by(km.DocumentationIndexJob.updated_at.desc()),
        _LIMITS["index_jobs"],
    )
    bounds["index_jobs"] = _bound(_LIMITS["index_jobs"], index_jobs, more)

    annotations, more = _bounded(
        db.query(gm.DocumentAnnotation).filter(
            gm.DocumentAnnotation.tenant_id == tenant.amo_id,
            gm.DocumentAnnotation.manual_id == manual.id,
            or_(gm.DocumentAnnotation.visibility != "PRIVATE", gm.DocumentAnnotation.created_by_user_id == current_user.id),
        ).order_by(gm.DocumentAnnotation.updated_at.desc()),
        _LIMITS["annotations"],
    )
    bounds["annotations"] = _bound(_LIMITS["annotations"], annotations, more)

    unresolved_responsibilities = int(db.query(func.count(gm.DocumentResponsibilityAssignment.id)).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
        gm.DocumentResponsibilityAssignment.manual_id == manual.id,
        gm.DocumentResponsibilityAssignment.confirmation_status.in_(["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]),
    ).scalar() or 0)
    unresolved_relationships = int(db.query(func.count(gm.DocumentGovernedRelationship.id)).filter(
        gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
        gm.DocumentGovernedRelationship.source_manual_id == manual.id,
        gm.DocumentGovernedRelationship.resolution_status.in_(["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]),
    ).scalar() or 0)
    unresolved_references = int(db.query(func.count(km.DocumentationReference.id)).filter(
        km.DocumentationReference.tenant_id == tenant.amo_id,
        km.DocumentationReference.source_manual_id == manual.id,
        km.DocumentationReference.status.in_(["UNRESOLVED", "AMBIGUOUS", "BROKEN", "OUTDATED", "AUTO_RESOLVED"]),
    ).scalar() or 0)

    today = date.today()
    active_types = {
        row[0]
        for row in db.query(gm.DocumentResponsibilityAssignment.responsibility_type).filter(
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.manual_id == manual.id,
            gm.DocumentResponsibilityAssignment.confirmation_status.notin_(["REJECTED", "SUPERSEDED"]),
            gm.DocumentResponsibilityAssignment.effective_from <= today,
            or_(gm.DocumentResponsibilityAssignment.effective_to.is_(None), gm.DocumentResponsibilityAssignment.effective_to >= today),
        ).distinct().all()
    }
    required = {"DOCUMENT_OWNER", "RESPONSIBLE_DEPARTMENT", "DOCUMENT_CONTROLLER", "QUALITY_REVIEWER", "APPROVER"}
    missing_responsibilities = sorted(required - active_types)
    structure, structure_bound = _bounded_structure(db, tenant_id=tenant.amo_id, manual_id=manual.id)
    bounds["structure_children"] = structure_bound

    issues: list[dict[str, Any]] = []
    if missing_responsibilities:
        issues.append({"code": "MISSING_RESPONSIBILITY", "severity": "HIGH", "count": len(missing_responsibilities), "items": missing_responsibilities})
    if not structure:
        issues.append({"code": "ORPHANED_STRUCTURE", "severity": "HIGH", "count": 1})
    if unresolved_references or unresolved_relationships:
        issues.append({"code": "UNRESOLVED_RELATIONSHIP", "severity": "MEDIUM", "count": unresolved_references + unresolved_relationships})
    if target and not target.source_sha256:
        issues.append({"code": "MISSING_SOURCE_CHECKSUM", "severity": "HIGH", "count": 1})

    assignment_options = {"users": [], "departments": [], "org_units": []}
    if service.is_control_user(current_user):
        from amodb.apps.workforce.governance_models import WorkforceOrgUnit

        option_users, more = _bounded(
            db.query(account_models.User).filter(
                account_models.User.amo_id == tenant.amo_id,
                account_models.User.is_active.is_(True),
                account_models.User.is_system_account.is_(False),
            ).order_by(account_models.User.full_name.asc()),
            _LIMITS["assignment_users"],
        )
        bounds["assignment_users"] = _bound(_LIMITS["assignment_users"], option_users, more)
        option_departments, more = _bounded(
            db.query(account_models.Department).filter(
                account_models.Department.amo_id == tenant.amo_id,
                account_models.Department.is_active.is_(True),
            ).order_by(account_models.Department.name.asc()),
            _LIMITS["assignment_departments"],
        )
        bounds["assignment_departments"] = _bound(_LIMITS["assignment_departments"], option_departments, more)
        option_org_units, more = _bounded(
            db.query(WorkforceOrgUnit).filter(
                WorkforceOrgUnit.amo_id == tenant.amo_id,
                WorkforceOrgUnit.is_active.is_(True),
            ).order_by(WorkforceOrgUnit.sort_order.asc(), WorkforceOrgUnit.name.asc()),
            _LIMITS["assignment_org_units"],
        )
        bounds["assignment_org_units"] = _bound(_LIMITS["assignment_org_units"], option_org_units, more)
        assignment_options = {
            "users": [{"id": row.id, "name": row.full_name, "email": row.email} for row in option_users],
            "departments": [{"id": row.id, "code": row.code, "name": row.name} for row in option_departments],
            "org_units": [{"id": row.id, "code": row.code, "name": row.name, "unit_type": row.unit_type} for row in option_org_units],
        }

    return {
        "document": service.serialize_manual(manual, profile, target, target_kind, revisions[0] if revisions else None),
        "revisions": [service.serialize_revision(row) for row in revisions],
        "responsibilities": [service.serialize_assignment(row, users=users, departments=departments) for row in assignments],
        "effective_responsibilities": {key: [service.serialize_assignment(row, users=users, departments=departments) for row in values] for key, values in grouped.items()},
        "structure": structure,
        "relationships": [service.serialize_relationship(row, manuals) for row in relationships],
        "detected_references": [service.serialize_reference(row, manuals) for row in references],
        "index_jobs": [service.serialize_index_job(row) for row in index_jobs],
        "assignment_options": assignment_options,
        "annotations": [{
            "id": row.id,
            "revision_id": row.revision_id,
            "location_id": row.location_id,
            "annotation_type": row.annotation_type,
            "color": row.color,
            "visibility": row.visibility,
            "note_text": row.note_text,
            "tags": list(row.tags_json or []),
            "linked_entity_type": row.linked_entity_type,
            "linked_entity_id": row.linked_entity_id,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in annotations],
        "issues": issues,
        "completeness": {
            "missing_responsibilities": missing_responsibilities,
            "unresolved_responsibilities": unresolved_responsibilities,
            "unresolved_relationships": unresolved_relationships + unresolved_references,
            "structure_complete": structure is not None,
            "indexing_status": index_jobs[0].status if index_jobs else "NOT_INDEXED",
        },
        "collection_bounds": bounds,
    }


def incoming_would_replace_confirmed_at(
    existing: Iterable[gm.DocumentResponsibilityAssignment],
    *,
    responsibility_type: str,
    assignment_source: str,
    confidence_percent: int,
    on_date: date | None = None,
) -> bool:
    if assignment_source not in {"INFERRED", "IMPORTED"}:
        return False
    evaluation_date = on_date or date.today()
    return any(
        row.responsibility_type == responsibility_type
        and row.confirmation_status == "CONFIRMED"
        and service.active_on(row, evaluation_date)
        and service.assignment_rank(row)[2] >= confidence_percent
        for row in existing
    )


def install() -> None:
    from . import governance_router

    service.incoming_would_replace_confirmed = incoming_would_replace_confirmed_at
    governance_router.incoming_would_replace_confirmed = incoming_would_replace_confirmed_at
    governance_router.document_governance_payload = bounded_document_governance_payload
