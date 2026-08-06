from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from . import domain_models as dm
from . import governance_models as gm
from . import knowledge_models as km
from .knowledge_service import serialize_index_job
from .workspace_service import can_read_manual, get_profile, is_control_user, readable_revision, serialize_manual, serialize_revision


RESPONSIBILITY_TYPES = {
    "BUSINESS_OWNER",
    "DOCUMENT_OWNER",
    "RESPONSIBLE_DEPARTMENT",
    "RESPONSIBLE_ORG_UNIT",
    "ACCOUNTABLE_ROLE",
    "RESPONSIBLE_PERSON",
    "DOCUMENT_CONTROLLER",
    "CUSTODIAN",
    "TECHNICAL_REVIEWER",
    "QUALITY_REVIEWER",
    "APPROVER",
    "DISTRIBUTION_ADMINISTRATOR",
    "RETENTION_OWNER",
    "FORM_OWNER",
}
ASSIGNEE_TYPES = {"USER", "DEPARTMENT", "ORG_UNIT", "ROLE"}
ASSIGNMENT_SOURCES = {"MANUAL", "INHERITED", "MIGRATED", "INFERRED", "IMPORTED"}
CONFIRMATION_STATES = {"DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT", "CONFIRMED", "REJECTED", "SUPERSEDED"}
RELATIONSHIP_TYPES = {
    "IMPLEMENTS", "SUPPORTS", "REFERENCES", "REFERENCED_BY", "REQUIRES", "REQUIRED_BY",
    "SUPERSEDES", "SUPERSEDED_BY", "AMENDS", "HAS_FORM", "FORM_FOR", "HAS_TEMPLATE",
    "HAS_CHECKLIST", "GENERATES_RECORD", "EVIDENCE_FOR", "CONTROLLED_BY", "OWNED_BY",
    "APPROVED_BY", "DISTRIBUTED_TO", "TRAINING_REQUIRED_BY", "LINKED_REGULATION",
    "LINKED_AUDIT", "LINKED_FINDING", "LINKED_CAR", "LINKED_CHANGE_PROPOSAL",
    "LINKED_WORK_ORDER", "LINKED_AIRCRAFT_OR_COMPONENT",
}
RELATIONSHIP_SOURCES = {"MANUAL", "EXTRACTED", "INFERRED", "IMPORTED", "MIGRATED"}
ANNOTATION_TYPES = {"HIGHLIGHT", "NOTE", "QUESTION", "EVIDENCE", "FINDING_LINK", "BOOKMARK"}
ANNOTATION_COLORS = {"YELLOW", "GREEN", "BLUE", "PINK", "RED"}
ANNOTATION_VISIBILITIES = {"PRIVATE", "TEAM", "AUDIT", "CONTROLLED_RECORD"}


def utcnow() -> datetime:
    return datetime.utcnow()


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def active_on(row: gm.DocumentResponsibilityAssignment, on_date: date | None = None) -> bool:
    on_date = on_date or date.today()
    return (
        row.confirmation_status not in {"REJECTED", "SUPERSEDED"}
        and row.effective_from <= on_date
        and (row.effective_to is None or row.effective_to >= on_date)
    )


def assignment_rank(row: gm.DocumentResponsibilityAssignment) -> tuple[int, int, int, datetime]:
    confirmation = 3 if row.confirmation_status == "CONFIRMED" else 2 if row.confirmation_status == "MATCH_PROPOSED" else 1
    source = {"MANUAL": 5, "IMPORTED": 4, "MIGRATED": 3, "INHERITED": 2, "INFERRED": 1}.get(row.assignment_source, 0)
    return confirmation, source, int(row.confidence_percent or 0), row.updated_at or row.created_at or datetime.min


def effective_assignments(rows: Iterable[gm.DocumentResponsibilityAssignment], on_date: date | None = None) -> dict[str, list[gm.DocumentResponsibilityAssignment]]:
    grouped: dict[str, list[gm.DocumentResponsibilityAssignment]] = {}
    for row in rows:
        if not active_on(row, on_date):
            continue
        grouped.setdefault(row.responsibility_type, []).append(row)
    for values in grouped.values():
        values.sort(key=assignment_rank, reverse=True)
    return grouped


def incoming_would_replace_confirmed(
    existing: Iterable[gm.DocumentResponsibilityAssignment],
    *,
    responsibility_type: str,
    assignment_source: str,
    confidence_percent: int,
) -> bool:
    if assignment_source not in {"INFERRED", "IMPORTED"}:
        return False
    for row in existing:
        if (
            row.responsibility_type == responsibility_type
            and row.confirmation_status == "CONFIRMED"
            and active_on(row)
            and assignment_rank(row)[2] >= confidence_percent
        ):
            return True
    return False


def validate_assignment_target(
    *,
    assignee_type: str,
    assignee_user_id: str | None,
    assignee_department_id: str | None,
    assignee_org_unit_id: str | None,
    assignee_role: str | None,
) -> None:
    if assignee_type not in ASSIGNEE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported assignee type")
    supplied = {
        "USER": bool(assignee_user_id),
        "DEPARTMENT": bool(assignee_department_id),
        "ORG_UNIT": bool(assignee_org_unit_id),
        "ROLE": bool(assignee_role and assignee_role.strip()),
    }
    if sum(supplied.values()) != 1 or not supplied[assignee_type]:
        raise HTTPException(status_code=422, detail="Exactly one assignee matching assignee_type is required")


def _user_labels(db: Session, ids: set[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    return {
        row.id: {"id": row.id, "name": row.full_name, "email": row.email}
        for row in db.query(account_models.User).filter(account_models.User.id.in_(ids)).all()
    }


def _department_labels(db: Session, ids: set[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    return {
        row.id: {"id": row.id, "code": row.code, "name": row.name}
        for row in db.query(account_models.Department).filter(account_models.Department.id.in_(ids)).all()
    }


def serialize_assignment(
    row: gm.DocumentResponsibilityAssignment,
    *,
    users: dict[str, dict[str, Any]] | None = None,
    departments: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    users = users or {}
    departments = departments or {}
    target: dict[str, Any]
    if row.assignee_type == "USER":
        target = users.get(row.assignee_user_id or "", {"id": row.assignee_user_id, "name": "Unavailable user"})
    elif row.assignee_type == "DEPARTMENT":
        target = departments.get(row.assignee_department_id or "", {"id": row.assignee_department_id, "name": "Unavailable department"})
    elif row.assignee_type == "ORG_UNIT":
        target = {"id": row.assignee_org_unit_id, "name": row.provenance_json.get("org_unit_name") or "Organization unit"}
    else:
        target = {"role": row.assignee_role, "name": (row.assignee_role or "Role").replace("_", " ").title()}
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "responsibility_type": row.responsibility_type,
        "assignee_type": row.assignee_type,
        "assignee": target,
        "is_primary": row.is_primary,
        "delegated_from_id": row.delegated_from_id,
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "assignment_source": row.assignment_source,
        "confidence_percent": row.confidence_percent,
        "confirmation_status": row.confirmation_status,
        "provenance": dict(row.provenance_json or {}),
        "created_by_user_id": row.created_by_user_id,
        "confirmed_by_user_id": row.confirmed_by_user_id,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def serialize_relationship(row: gm.DocumentGovernedRelationship, manuals: dict[str, manual_models.Manual] | None = None) -> dict[str, Any]:
    manuals = manuals or {}
    target_manual = manuals.get(row.target_manual_id or "")
    return {
        "id": row.id,
        "source_manual_id": row.source_manual_id,
        "source_revision_id": row.source_revision_id,
        "source_location_id": row.source_location_id,
        "target_entity_type": row.target_entity_type,
        "target_entity_id": row.target_entity_id,
        "target_manual": ({"id": target_manual.id, "code": target_manual.code, "title": target_manual.title} if target_manual else None),
        "target_revision_id": row.target_revision_id,
        "relationship_type": row.relationship_type,
        "relationship_source": row.relationship_source,
        "exact_token": row.exact_token,
        "exact_quote": row.exact_quote,
        "page_number": row.page_number,
        "section_label": row.section_label,
        "confidence_percent": row.confidence_percent,
        "resolution_status": row.resolution_status,
        "provenance": dict(row.provenance_json or {}),
        "confirmed_by_user_id": row.confirmed_by_user_id,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def serialize_reference(row: km.DocumentationReference, manuals: dict[str, manual_models.Manual]) -> dict[str, Any]:
    target = manuals.get(row.target_manual_id or "")
    return {
        "id": row.id,
        "kind": "DETECTED_REFERENCE",
        "raw_token": row.raw_token,
        "normalized_token": row.normalized_token,
        "relationship_type": row.relationship_type,
        "status": row.status,
        "confidence_percent": row.confidence_percent,
        "detection_method": row.detection_method,
        "source_revision_id": row.source_revision_id,
        "source_page_number": row.source_page_number,
        "source_quote": row.source_quote,
        "source_context": row.source_context,
        "target_manual": ({"id": target.id, "code": target.code, "title": target.title} if target else None),
        "target_revision_id": row.target_revision_id,
        "candidates": list(row.candidates_json or []),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _structure_for_manual(db: Session, *, tenant_id: str, manual_id: str) -> dict[str, Any] | None:
    row = db.query(km.DocumentationNode).filter(
        km.DocumentationNode.tenant_id == tenant_id,
        km.DocumentationNode.manual_id == manual_id,
    ).first()
    if not row:
        return None
    children = db.query(km.DocumentationNode).filter(
        km.DocumentationNode.tenant_id == tenant_id,
        km.DocumentationNode.parent_id == row.id,
    ).order_by(km.DocumentationNode.order_index.asc()).all()
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
    }


def document_governance_payload(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    current_user: account_models.User,
) -> dict[str, Any]:
    profile = get_profile(db, tenant, manual.id)
    if not can_read_manual(current_user, profile):
        raise HTTPException(status_code=403, detail="Document access denied")
    target, target_kind = readable_revision(db, manual, current_user)
    revisions = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.manual_id == manual.id,
    ).order_by(manual_models.ManualRevision.created_at.desc()).all()
    assignments = db.query(gm.DocumentResponsibilityAssignment).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
        gm.DocumentResponsibilityAssignment.manual_id == manual.id,
    ).order_by(gm.DocumentResponsibilityAssignment.responsibility_type.asc(), gm.DocumentResponsibilityAssignment.created_at.desc()).all()
    user_ids = {row.assignee_user_id for row in assignments if row.assignee_user_id}
    department_ids = {row.assignee_department_id for row in assignments if row.assignee_department_id}
    users = _user_labels(db, user_ids)
    departments = _department_labels(db, department_ids)
    grouped = effective_assignments(assignments)

    relationships = db.query(gm.DocumentGovernedRelationship).filter(
        gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
        gm.DocumentGovernedRelationship.source_manual_id == manual.id,
    ).order_by(gm.DocumentGovernedRelationship.updated_at.desc()).all()
    references = db.query(km.DocumentationReference).filter(
        km.DocumentationReference.tenant_id == tenant.amo_id,
        km.DocumentationReference.source_manual_id == manual.id,
    ).order_by(km.DocumentationReference.updated_at.desc()).all()
    target_manual_ids = {row.target_manual_id for row in relationships if row.target_manual_id} | {row.target_manual_id for row in references if row.target_manual_id}
    manuals = {row.id: row for row in db.query(manual_models.Manual).filter(manual_models.Manual.id.in_(target_manual_ids or ["-"])).all()}
    index_jobs = db.query(km.DocumentationIndexJob).filter(
        km.DocumentationIndexJob.tenant_id == tenant.amo_id,
        km.DocumentationIndexJob.manual_id == manual.id,
    ).order_by(km.DocumentationIndexJob.updated_at.desc()).all()
    annotations = db.query(gm.DocumentAnnotation).filter(
        gm.DocumentAnnotation.tenant_id == tenant.amo_id,
        gm.DocumentAnnotation.manual_id == manual.id,
        or_(
            gm.DocumentAnnotation.visibility != "PRIVATE",
            gm.DocumentAnnotation.created_by_user_id == current_user.id,
        ),
    ).order_by(gm.DocumentAnnotation.updated_at.desc()).limit(250).all()

    unresolved_responsibilities = sum(1 for row in assignments if row.confirmation_status in {"DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"})
    unresolved_relationships = sum(1 for row in relationships if row.resolution_status in {"DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"})
    unresolved_references = sum(1 for row in references if row.status in {"UNRESOLVED", "AMBIGUOUS", "BROKEN", "OUTDATED", "AUTO_RESOLVED"})
    required = {"DOCUMENT_OWNER", "RESPONSIBLE_DEPARTMENT", "DOCUMENT_CONTROLLER", "QUALITY_REVIEWER", "APPROVER"}
    missing_responsibilities = sorted(required - set(grouped))
    issues: list[dict[str, Any]] = []
    if missing_responsibilities:
        issues.append({"code": "MISSING_RESPONSIBILITY", "severity": "HIGH", "count": len(missing_responsibilities), "items": missing_responsibilities})
    if not _structure_for_manual(db, tenant_id=tenant.amo_id, manual_id=manual.id):
        issues.append({"code": "ORPHANED_STRUCTURE", "severity": "HIGH", "count": 1})
    if unresolved_references or unresolved_relationships:
        issues.append({"code": "UNRESOLVED_RELATIONSHIP", "severity": "MEDIUM", "count": unresolved_references + unresolved_relationships})
    if target and not target.source_sha256:
        issues.append({"code": "MISSING_SOURCE_CHECKSUM", "severity": "HIGH", "count": 1})

    assignment_options = {"users": [], "departments": [], "org_units": []}
    if is_control_user(current_user):
        from amodb.apps.workforce.governance_models import WorkforceOrgUnit

        assignment_options = {
            "users": [
                {"id": row.id, "name": row.full_name, "email": row.email}
                for row in db.query(account_models.User).filter(
                    account_models.User.amo_id == tenant.amo_id,
                    account_models.User.is_active.is_(True),
                    account_models.User.is_system_account.is_(False),
                ).order_by(account_models.User.full_name.asc()).limit(1000).all()
            ],
            "departments": [
                {"id": row.id, "code": row.code, "name": row.name}
                for row in db.query(account_models.Department).filter(
                    account_models.Department.amo_id == tenant.amo_id,
                    account_models.Department.is_active.is_(True),
                ).order_by(account_models.Department.name.asc()).all()
            ],
            "org_units": [
                {"id": row.id, "code": row.code, "name": row.name, "unit_type": row.unit_type}
                for row in db.query(WorkforceOrgUnit).filter(
                    WorkforceOrgUnit.amo_id == tenant.amo_id,
                    WorkforceOrgUnit.is_active.is_(True),
                ).order_by(WorkforceOrgUnit.sort_order.asc(), WorkforceOrgUnit.name.asc()).limit(2000).all()
            ],
        }

    return {
        "document": serialize_manual(manual, profile, target, target_kind, revisions[0] if revisions else None),
        "revisions": [serialize_revision(row) for row in revisions],
        "responsibilities": [serialize_assignment(row, users=users, departments=departments) for row in assignments],
        "effective_responsibilities": {
            key: [serialize_assignment(row, users=users, departments=departments) for row in values]
            for key, values in grouped.items()
        },
        "structure": _structure_for_manual(db, tenant_id=tenant.amo_id, manual_id=manual.id),
        "relationships": [serialize_relationship(row, manuals) for row in relationships],
        "detected_references": [serialize_reference(row, manuals) for row in references],
        "index_jobs": [serialize_index_job(row) for row in index_jobs],
        "assignment_options": assignment_options,
        "annotations": [
            {
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
            }
            for row in annotations
        ],
        "issues": issues,
        "completeness": {
            "missing_responsibilities": missing_responsibilities,
            "unresolved_responsibilities": unresolved_responsibilities,
            "unresolved_relationships": unresolved_relationships + unresolved_references,
            "structure_complete": not any(item["code"] == "ORPHANED_STRUCTURE" for item in issues),
            "indexing_status": index_jobs[0].status if index_jobs else "NOT_INDEXED",
        },
    }


def governance_dashboard(db: Session, *, tenant: manual_models.Tenant) -> dict[str, Any]:
    amo_id = tenant.amo_id
    unresolved_owner = db.query(func.count(func.distinct(gm.DocumentResponsibilityAssignment.manual_id))).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == amo_id,
        gm.DocumentResponsibilityAssignment.responsibility_type.in_(["DOCUMENT_OWNER", "RESPONSIBLE_DEPARTMENT"]),
        gm.DocumentResponsibilityAssignment.confirmation_status.in_(["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]),
    ).scalar() or 0
    unresolved_relationships = db.query(func.count(gm.DocumentGovernedRelationship.id)).filter(
        gm.DocumentGovernedRelationship.tenant_id == amo_id,
        gm.DocumentGovernedRelationship.resolution_status.in_(["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]),
    ).scalar() or 0
    unresolved_references = db.query(func.count(km.DocumentationReference.id)).filter(
        km.DocumentationReference.tenant_id == amo_id,
        km.DocumentationReference.status.in_(["UNRESOLVED", "AMBIGUOUS", "BROKEN", "OUTDATED", "AUTO_RESOLVED"]),
    ).scalar() or 0
    failed_indexing = db.query(func.count(km.DocumentationIndexJob.id)).filter(
        km.DocumentationIndexJob.tenant_id == amo_id,
        km.DocumentationIndexJob.status == "FAILED",
    ).scalar() or 0
    orphaned = db.query(func.count(km.DocumentationNode.id)).filter(
        km.DocumentationNode.tenant_id == amo_id,
        km.DocumentationNode.manual_id.isnot(None),
        km.DocumentationNode.parent_id.is_(None),
        km.DocumentationNode.node_type != "ROOT",
    ).scalar() or 0
    superseded_referenced = db.query(func.count(km.DocumentationReference.id)).join(
        manual_models.ManualRevision,
        manual_models.ManualRevision.id == km.DocumentationReference.target_revision_id,
    ).filter(
        km.DocumentationReference.tenant_id == amo_id,
        manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.SUPERSEDED,
        km.DocumentationReference.status == "VERIFIED",
    ).scalar() or 0
    metrics = {
        "ownership_review": int(unresolved_owner),
        "relationship_review": int(unresolved_relationships + unresolved_references),
        "failed_indexing": int(failed_indexing),
        "orphaned_structure": int(orphaned),
        "superseded_references": int(superseded_referenced),
    }
    queues = [
        {"id": "ownership", "label": "Ownership requiring confirmation", "count": metrics["ownership_review"], "filter": {"unresolved_ownership": "true"}},
        {"id": "relationships", "label": "Detected relationships requiring review", "count": metrics["relationship_review"], "filter": {"unresolved_relationships": "true"}},
        {"id": "indexing", "label": "Failed indexing", "count": metrics["failed_indexing"], "filter": {"indexing_status": "FAILED"}},
        {"id": "structure", "label": "Orphaned structure nodes", "count": metrics["orphaned_structure"], "filter": {"structure_status": "ORPHANED"}},
        {"id": "superseded", "label": "Superseded documents still referenced", "count": metrics["superseded_references"], "filter": {"superseded_referenced": "true"}},
    ]
    return {"metrics": metrics, "queues": queues}


def governance_library(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    current_user: account_models.User,
    q: str | None,
    document_type: str | None,
    lifecycle_status: str | None,
    control_status: str | None,
    owner_user_id: str | None,
    department_id: str | None,
    indexing_status: str | None,
    unresolved_ownership: bool,
    unresolved_relationships: bool,
    superseded: bool | None,
    sort: str,
    direction: str,
    page: int,
    per_page: int,
) -> dict[str, Any]:
    query = db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id)
    if q:
        token = f"%{q.strip()}%"
        matching_revision = exists().where(and_(
            manual_models.ManualRevision.manual_id == manual_models.Manual.id,
            manual_models.ManualRevision.source_filename.ilike(token),
        ))
        matching_reference = exists().where(and_(
            km.DocumentationReference.source_manual_id == manual_models.Manual.id,
            km.DocumentationReference.tenant_id == tenant.amo_id,
            or_(km.DocumentationReference.raw_token.ilike(token), km.DocumentationReference.normalized_token.ilike(token)),
        ))
        query = query.filter(or_(manual_models.Manual.code.ilike(token), manual_models.Manual.title.ilike(token), matching_revision, matching_reference))
    if document_type:
        query = query.filter(manual_models.Manual.manual_type == document_type)
    if lifecycle_status:
        query = query.filter(manual_models.Manual.status == lifecycle_status)
    if superseded is not None:
        query = query.filter(manual_models.Manual.status == "SUPERSEDED" if superseded else manual_models.Manual.status != "SUPERSEDED")
    if control_status:
        profile_exists = exists().where(and_(
            dm.DocumentControlProfile.manual_id == manual_models.Manual.id,
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.document_class == control_status,
        ))
        query = query.filter(profile_exists)
    if owner_user_id or department_id or unresolved_ownership:
        assignment_filters = [
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.manual_id == manual_models.Manual.id,
            gm.DocumentResponsibilityAssignment.responsibility_type.in_(["DOCUMENT_OWNER", "RESPONSIBLE_DEPARTMENT"]),
        ]
        if owner_user_id:
            assignment_filters.append(gm.DocumentResponsibilityAssignment.assignee_user_id == owner_user_id)
        if department_id:
            assignment_filters.append(gm.DocumentResponsibilityAssignment.assignee_department_id == department_id)
        if unresolved_ownership:
            assignment_filters.append(
                gm.DocumentResponsibilityAssignment.confirmation_status.in_(
                    ["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]
                )
            )
        query = query.filter(exists().where(and_(*assignment_filters)))
    if indexing_status:
        query = query.filter(exists().where(and_(
            km.DocumentationIndexJob.manual_id == manual_models.Manual.id,
            km.DocumentationIndexJob.tenant_id == tenant.amo_id,
            km.DocumentationIndexJob.status == indexing_status,
        )))
    if unresolved_relationships:
        unresolved_reference = exists().where(and_(
            km.DocumentationReference.source_manual_id == manual_models.Manual.id,
            km.DocumentationReference.tenant_id == tenant.amo_id,
            km.DocumentationReference.status.in_(["UNRESOLVED", "AMBIGUOUS", "BROKEN", "OUTDATED", "AUTO_RESOLVED"]),
        ))
        unresolved_relation = exists().where(and_(
            gm.DocumentGovernedRelationship.source_manual_id == manual_models.Manual.id,
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            gm.DocumentGovernedRelationship.resolution_status.in_(["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]),
        ))
        query = query.filter(or_(unresolved_reference, unresolved_relation))

    sort_map = {"code": manual_models.Manual.code, "title": manual_models.Manual.title, "type": manual_models.Manual.manual_type, "status": manual_models.Manual.status}
    column = sort_map.get(sort, manual_models.Manual.code)
    query = query.order_by(column.desc() if direction.lower() == "desc" else column.asc(), manual_models.Manual.id.asc())
    if is_control_user(current_user):
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
    else:
        candidates = query.all()
        visible = [
            manual
            for manual in candidates
            if can_read_manual(current_user, get_profile(db, tenant, manual.id))
        ]
        total = len(visible)
        start = (page - 1) * per_page
        rows = visible[start:start + per_page]
    manual_ids = [row.id for row in rows]
    profiles = {row.manual_id: row for row in db.query(dm.DocumentControlProfile).filter(dm.DocumentControlProfile.manual_id.in_(manual_ids or ["-"])).all()}
    revisions = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.manual_id.in_(manual_ids or ["-"])).order_by(manual_models.ManualRevision.created_at.desc()).all()
    latest: dict[str, manual_models.ManualRevision] = {}
    for revision in revisions:
        latest.setdefault(revision.manual_id, revision)
    assignments = db.query(gm.DocumentResponsibilityAssignment).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
        gm.DocumentResponsibilityAssignment.manual_id.in_(manual_ids or ["-"]),
    ).all()
    grouped_by_manual: dict[str, list[gm.DocumentResponsibilityAssignment]] = {}
    for assignment in assignments:
        grouped_by_manual.setdefault(assignment.manual_id, []).append(assignment)
    user_ids = {row.assignee_user_id for row in assignments if row.assignee_user_id}
    dept_ids = {row.assignee_department_id for row in assignments if row.assignee_department_id}
    users = _user_labels(db, user_ids)
    departments = _department_labels(db, dept_ids)
    reference_counts = dict(db.query(km.DocumentationReference.source_manual_id, func.count(km.DocumentationReference.id)).filter(
        km.DocumentationReference.source_manual_id.in_(manual_ids or ["-"]),
        km.DocumentationReference.status.in_(["UNRESOLVED", "AMBIGUOUS", "BROKEN", "OUTDATED", "AUTO_RESOLVED"]),
    ).group_by(km.DocumentationReference.source_manual_id).all())
    relationship_counts = dict(db.query(gm.DocumentGovernedRelationship.source_manual_id, func.count(gm.DocumentGovernedRelationship.id)).filter(
        gm.DocumentGovernedRelationship.source_manual_id.in_(manual_ids or ["-"]),
        gm.DocumentGovernedRelationship.resolution_status.in_(["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"]),
    ).group_by(gm.DocumentGovernedRelationship.source_manual_id).all())
    jobs = {row.manual_id: row for row in db.query(km.DocumentationIndexJob).filter(km.DocumentationIndexJob.manual_id.in_(manual_ids or ["-"])).order_by(km.DocumentationIndexJob.updated_at.asc()).all()}
    nodes = {row.manual_id: row for row in db.query(km.DocumentationNode).filter(km.DocumentationNode.manual_id.in_(manual_ids or ["-"])).all()}

    items = []
    for manual in rows:
        profile = profiles.get(manual.id)
        if not can_read_manual(current_user, profile):
            continue
        active = effective_assignments(grouped_by_manual.get(manual.id, []))
        owner = (active.get("DOCUMENT_OWNER") or active.get("BUSINESS_OWNER") or [None])[0]
        department = (active.get("RESPONSIBLE_DEPARTMENT") or [None])[0]
        latest_revision = latest.get(manual.id)
        items.append({
            "id": manual.id,
            "code": manual.code,
            "title": manual.title,
            "document_type": manual.manual_type,
            "lifecycle_status": manual.status,
            "control_status": profile.document_class if profile else "INTERNAL",
            "issue_number": latest_revision.issue_number if latest_revision else None,
            "revision_number": latest_revision.rev_number if latest_revision else None,
            "effective_date": latest_revision.effective_date.isoformat() if latest_revision and latest_revision.effective_date else None,
            "source_format": _value(latest_revision.source_type_enum) if latest_revision else None,
            "owner": serialize_assignment(owner, users=users, departments=departments) if owner else None,
            "responsible_department": serialize_assignment(department, users=users, departments=departments) if department else None,
            "unresolved_ownership": sum(1 for row in grouped_by_manual.get(manual.id, []) if row.confirmation_status in {"DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"}),
            "unresolved_relationships": int(reference_counts.get(manual.id, 0)) + int(relationship_counts.get(manual.id, 0)),
            "indexing_status": jobs.get(manual.id).status if jobs.get(manual.id) else "NOT_INDEXED",
            "structure_path": nodes.get(manual.id).path if nodes.get(manual.id) else None,
            "superseded": manual.status == "SUPERSEDED",
        })
    return {"items": items, "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(items)}}


def sha256_for_revision(revision: manual_models.ManualRevision) -> str | None:
    if revision.source_sha256:
        return revision.source_sha256
    if not revision.source_storage_path:
        return None
    path = Path(revision.source_storage_path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_legacy_responsibility_proposals(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    profile: dm.DocumentControlProfile | None,
    actor_id: str | None,
    dry_run: bool,
) -> list[dict[str, Any]]:
    existing = db.query(gm.DocumentResponsibilityAssignment).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
        gm.DocumentResponsibilityAssignment.manual_id == manual.id,
    ).all()
    proposals: list[dict[str, Any]] = []

    def propose(responsibility_type: str, assignee_type: str, *, user_id: str | None = None, department_id: str | None = None, role: str | None = None, source: str, status: str, confidence: int, provenance: dict[str, Any]) -> None:
        if any(row.responsibility_type == responsibility_type and row.confirmation_status == "CONFIRMED" for row in existing):
            return
        target_value = user_id or department_id or role
        if not target_value:
            return
        proposal = {"responsibility_type": responsibility_type, "assignee_type": assignee_type, "target": target_value, "source": source, "status": status, "confidence": confidence}
        proposals.append(proposal)
        if dry_run:
            return
        row = gm.DocumentResponsibilityAssignment(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            responsibility_type=responsibility_type,
            assignee_type=assignee_type,
            assignee_user_id=user_id,
            assignee_department_id=department_id,
            assignee_role=role,
            effective_from=date.today(),
            assignment_source=source,
            confidence_percent=confidence,
            confirmation_status=status,
            provenance_json=provenance,
            created_by_user_id=actor_id,
            confirmed_by_user_id=actor_id if status == "CONFIRMED" else None,
            confirmed_at=utcnow() if status == "CONFIRMED" else None,
        )
        db.add(row)
        existing.append(row)

    if profile and profile.owner_user_id:
        propose("DOCUMENT_OWNER", "USER", user_id=profile.owner_user_id, source="MIGRATED", status="CONFIRMED", confidence=100, provenance={"legacy_field": "document_control_profiles.owner_user_id"})
    if profile and profile.owner_department:
        department = db.query(account_models.Department).filter(
            account_models.Department.amo_id == tenant.amo_id,
            account_models.Department.code == profile.owner_department,
        ).first()
        if department:
            propose("RESPONSIBLE_DEPARTMENT", "DEPARTMENT", department_id=department.id, source="MIGRATED", status="CONFIRMED", confidence=100, provenance={"legacy_field": "document_control_profiles.owner_department"})
        else:
            propose("RESPONSIBLE_DEPARTMENT", "ROLE", role=profile.owner_department, source="INFERRED", status="MATCH_PROPOSED", confidence=65, provenance={"legacy_field": "document_control_profiles.owner_department", "reason": "No canonical department code match"})
    if manual.owner_role:
        propose("ACCOUNTABLE_ROLE", "ROLE", role=manual.owner_role, source="MIGRATED", status="CONFIRMED", confidence=100, provenance={"legacy_field": "manuals.owner_role"})
    propose("DOCUMENT_CONTROLLER", "ROLE", role="DOCUMENT_CONTROLLER", source="INFERRED", status="MATCH_PROPOSED", confidence=55, provenance={"reason": "Legacy Document Control default; confirmation required"})
    return proposals


def process_backfill_document(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    actor_id: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    profile = get_profile(db, tenant, manual.id)
    revision = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.manual_id == manual.id,
    ).order_by(manual_models.ManualRevision.created_at.desc()).first()
    result: dict[str, Any] = {"manual_id": manual.id, "code": manual.code, "actions": []}
    checksum = sha256_for_revision(revision) if revision else None
    if revision and checksum and not revision.source_sha256:
        result["actions"].append({"action": "SET_SOURCE_CHECKSUM", "revision_id": revision.id, "sha256": checksum})
        if not dry_run:
            revision.source_sha256 = checksum
    elif revision and not checksum:
        result["actions"].append({"action": "CHECKSUM_UNAVAILABLE", "revision_id": revision.id})
    proposals = ensure_legacy_responsibility_proposals(db, tenant=tenant, manual=manual, profile=profile, actor_id=actor_id, dry_run=dry_run)
    result["actions"].extend({"action": "RESPONSIBILITY", **proposal} for proposal in proposals)
    if dry_run and not db.query(km.DocumentationNode.id).filter(
        km.DocumentationNode.tenant_id == tenant.amo_id,
        km.DocumentationNode.manual_id == manual.id,
    ).first():
        result["actions"].append({"action": "CREATE_HIERARCHY_NODE"})
    if revision:
        job = db.query(km.DocumentationIndexJob).filter(
            km.DocumentationIndexJob.tenant_id == tenant.amo_id,
            km.DocumentationIndexJob.revision_id == revision.id,
        ).first()
        if not job:
            result["actions"].append({"action": "CREATE_INDEX_JOB", "revision_id": revision.id})
            if not dry_run:
                db.add(km.DocumentationIndexJob(
                    tenant_id=tenant.amo_id,
                    manual_id=manual.id,
                    revision_id=revision.id,
                    source_sha256=checksum,
                    status="PENDING",
                ))
        elif checksum and job.source_sha256 != checksum:
            result["actions"].append({"action": "RESET_STALE_INDEX", "revision_id": revision.id})
            if not dry_run:
                job.source_sha256 = checksum
                job.status = "PENDING"
                job.error_summary = None
    return result
