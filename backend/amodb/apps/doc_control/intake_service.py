from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from . import domain_models as dm
from . import governance_models as gm
from . import knowledge_models as km
from .knowledge_service import (
    EXECUTABLE_NODE_TYPES,
    _default_group_code,
    normalize_code,
    reconcile_documentation_hierarchy,
    update_subtree_paths,
    validate_hierarchy_move,
)


DOCUMENT_TYPES = {
    "MANUAL",
    "REGULATION",
    "POLICY",
    "PROCEDURE",
    "WORK_INSTRUCTION",
    "FORM",
    "CHECKLIST",
    "REGISTER",
    "RECORD",
    "EXTERNAL_DOCUMENT",
}

TYPE_STORAGE_VALUE = {
    "MANUAL": "MANUAL",
    "REGULATION": "REGULATION",
    "POLICY": "POLICY",
    "PROCEDURE": "PROCEDURE",
    "WORK_INSTRUCTION": "WORK INSTRUCTION",
    "FORM": "FORM",
    "CHECKLIST": "CHECKLIST",
    "REGISTER": "REGISTER",
    "RECORD": "RECORD",
    "EXTERNAL_DOCUMENT": "EXTERNAL DOCUMENT",
}


def parse_intake_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Controlled-document metadata must be valid JSON.") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="Controlled-document metadata must be a JSON object.")
    return value


def _text(value: Any, *, max_length: int = 255) -> str | None:
    result = str(value or "").strip()
    return result[:max_length] if result else None


def _date(value: Any, field: str) -> date | None:
    text = _text(value, max_length=32)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} must use YYYY-MM-DD format.") from exc


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int | None:
    if value in (None, ""):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be a whole number.") from exc
    if result < minimum or result > maximum:
        raise HTTPException(status_code=422, detail=f"{field} must be between {minimum} and {maximum}.")
    return result


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _document_node(db: Session, *, tenant_id: str, manual_id: str) -> km.DocumentationNode | None:
    return db.query(km.DocumentationNode).filter(
        km.DocumentationNode.tenant_id == tenant_id,
        km.DocumentationNode.manual_id == manual_id,
    ).first()


def _profile(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
) -> dm.DocumentControlProfile:
    row = db.query(dm.DocumentControlProfile).filter(
        dm.DocumentControlProfile.tenant_id == tenant.amo_id,
        dm.DocumentControlProfile.manual_id == manual.id,
    ).first()
    if row:
        return row
    row = dm.DocumentControlProfile(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        owner_department=manual.owner_role or "DOCUMENT_CONTROL",
    )
    db.add(row)
    db.flush()
    return row


def _relationship_type(document_type: str, parent_type: str) -> str:
    if parent_type == "REGULATION":
        return "LINKED_REGULATION"
    if document_type in {"PROCEDURE", "WORK_INSTRUCTION"}:
        return "IMPLEMENTS"
    if document_type in {"FORM", "CHECKLIST", "REGISTER"}:
        return "SUPPORTS"
    if document_type == "RECORD":
        return "EVIDENCE_FOR"
    return "REFERENCES"


def apply_controlled_document_metadata(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    user: account_models.User,
    metadata: dict[str, Any],
    origin: str,
) -> dict[str, Any]:
    """Apply confirmed intake metadata to the canonical DMS record in one transaction."""
    document_type = str(metadata.get("document_type") or manual.manual_type or "MANUAL").strip().upper().replace(" ", "_")
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported documented-information type: {document_type}.")

    profile = _profile(db, tenant=tenant, manual=manual)
    owner_department = _text(metadata.get("owner_department"), max_length=128)
    if owner_department:
        profile.owner_department = owner_department
        manual.owner_role = owner_department

    document_class = str(metadata.get("document_class") or "").strip().upper()
    if document_type in {"REGULATION", "EXTERNAL_DOCUMENT"}:
        document_class = "EXTERNAL"
    elif document_type == "RECORD":
        document_class = "RECORD"
    elif document_class not in {"INTERNAL", "EXTERNAL", "RECORD"}:
        document_class = profile.document_class or "INTERNAL"
    profile.document_class = document_class

    maximum_review_months = 12 if document_type == "CHECKLIST" else 24
    review_interval = _integer(
        metadata.get("review_interval_months"),
        "Review interval",
        minimum=1,
        maximum=maximum_review_months,
    )
    retention_years = _integer(metadata.get("retention_years"), "Retention period", minimum=1, maximum=100)
    if retention_years is None and document_type == "RECORD":
        retention_years = 5
    profile.review_interval_months = review_interval or maximum_review_months
    maximum_review_due = _add_months(date.today(), maximum_review_months)
    profile.next_review_due = _date(metadata.get("next_review_due"), "Next review date") or _add_months(
        date.today(), profile.review_interval_months
    )
    if profile.next_review_due > maximum_review_due:
        raise HTTPException(
            status_code=422,
            detail=f"Next review date cannot be more than {maximum_review_months} months from today for this document type.",
        )
    profile.acknowledgement_required = bool(metadata.get("acknowledgement_required", profile.acknowledgement_required))

    confidentiality = str(metadata.get("confidentiality") or "INTERNAL").strip().upper()
    if confidentiality not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        raise HTTPException(status_code=422, detail="Unsupported confidentiality classification.")
    profile.restricted_flag = confidentiality in {"CONFIDENTIAL", "RESTRICTED"}
    profile.regulated_flag = bool(metadata.get("regulated_flag", profile.regulated_flag)) or document_type == "REGULATION"

    raw_tags = metadata.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split(",")
    profile.tags_json = list(dict.fromkeys(
        tag for tag in (_text(item, max_length=64) for item in raw_tags if item is not None) if tag
    ))[:50]
    profile.metadata_json = {
        **dict(profile.metadata_json or {}),
        "document_type_override": document_type,
        "description": _text(metadata.get("description"), max_length=4000),
        "source_issuer": _text(metadata.get("source_issuer"), max_length=255),
        "confidentiality": confidentiality,
        "retention_years": retention_years,
        "parent_document_id": _text(metadata.get("parent_document_id"), max_length=36),
        "intake_origin": origin,
        "metadata_confirmed_by_user_id": str(user.id),
        "metadata_confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    profile.version = int(profile.version or 0) + 1
    manual.manual_type = TYPE_STORAGE_VALUE[document_type]

    # Materialize the canonical node before validating a user-confirmed parent.
    reconcile_documentation_hierarchy(db, manual_tenant=tenant, actor_id=str(user.id))
    node = _document_node(db, tenant_id=str(tenant.amo_id), manual_id=manual.id)
    if node is None:
        raise HTTPException(status_code=500, detail="The controlled document hierarchy node could not be created.")
    node.node_type = document_type
    node.code = manual.code
    node.normalized_code = normalize_code(manual.code)
    node.title = manual.title
    node.metadata_json = {
        **dict(node.metadata_json or {}),
        "document_type_override": document_type,
        "metadata_confirmed": True,
    }

    parent_document_id = _text(metadata.get("parent_document_id"), max_length=36)
    parent_node = None

    # Every metadata confirmation replaces the prior direct lineage decision.
    # This also makes selecting "no direct parent" meaningful instead of leaving
    # a stale manual/procedure relationship active from an earlier classification.
    db.query(gm.DocumentGovernedRelationship).filter(
        gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
        gm.DocumentGovernedRelationship.source_manual_id == manual.id,
        gm.DocumentGovernedRelationship.occurrence_key.like(f"hierarchy:{manual.id}:%"),
        gm.DocumentGovernedRelationship.resolution_status != "SUPERSEDED",
    ).update({"resolution_status": "SUPERSEDED"}, synchronize_session=False)

    if parent_document_id:
        parent = db.query(manual_models.Manual).filter(
            manual_models.Manual.id == parent_document_id,
            manual_models.Manual.tenant_id == tenant.id,
        ).first()
        if parent is None:
            raise HTTPException(status_code=422, detail="The selected parent document is not in this AMO's controlled library.")
        if parent.id == manual.id:
            raise HTTPException(status_code=409, detail="A controlled document cannot be its own parent.")
        parent_node = _document_node(db, tenant_id=str(tenant.amo_id), manual_id=parent.id)
        if parent_node is None:
            raise HTTPException(status_code=409, detail="The selected parent document has no governed hierarchy node.")
        validate_hierarchy_move(
            db,
            tenant_id=str(tenant.amo_id),
            node=node,
            parent=parent_node,
            node_type=document_type,
        )
        node.parent_id = parent_node.id
        update_subtree_paths(db, node, parent_node)
        occurrence_key = f"hierarchy:{manual.id}:{parent.id}"
        relation = db.query(gm.DocumentGovernedRelationship).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            gm.DocumentGovernedRelationship.occurrence_key == occurrence_key,
        ).first()
        if relation is None:
            relation = gm.DocumentGovernedRelationship(
                tenant_id=tenant.amo_id,
                source_manual_id=manual.id,
                target_entity_type="CONTROLLED_DOCUMENT",
                target_entity_id=parent.id,
                target_manual_id=parent.id,
                relationship_type=_relationship_type(document_type, parent_node.node_type),
                relationship_source="MANUAL",
                occurrence_key=occurrence_key,
                exact_token=parent.code,
                confidence_percent=100,
                resolution_status="CONFIRMED",
                provenance_json={"intake_hierarchy": True, "origin": origin},
                created_by_user_id=user.id,
                confirmed_by_user_id=user.id,
                confirmed_at=datetime.now(timezone.utc),
            )
            db.add(relation)
        else:
            relation.resolution_status = "CONFIRMED"
            relation.relationship_type = _relationship_type(document_type, parent_node.node_type)
            relation.confirmed_by_user_id = user.id
            relation.confirmed_at = datetime.now(timezone.utc)
    else:
        group_code = _default_group_code(document_type, manual, profile)
        group_node = db.query(km.DocumentationNode).filter(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.normalized_code == normalize_code(group_code),
            km.DocumentationNode.status == "ACTIVE",
            km.DocumentationNode.manual_id.is_(None),
        ).first()
        if group_node is None:
            raise HTTPException(status_code=500, detail="The standard document hierarchy group could not be resolved.")
        validate_hierarchy_move(
            db,
            tenant_id=str(tenant.amo_id),
            node=node,
            parent=group_node,
            node_type=document_type,
        )
        node.parent_id = group_node.id
        update_subtree_paths(db, node, group_node)

    if document_type not in EXECUTABLE_NODE_TYPES:
        execution = db.query(km.DocumentationExecutionProfile).filter(
            km.DocumentationExecutionProfile.tenant_id == tenant.amo_id,
            km.DocumentationExecutionProfile.manual_id == manual.id,
        ).first()
        if execution:
            db.delete(execution)

    db.flush()
    return {
        "document_type": document_type,
        "document_class": profile.document_class,
        "profile_id": profile.id,
        "hierarchy_node_id": node.id,
        "hierarchy_parent_id": parent_node.id if parent_node else node.parent_id,
        "hierarchy_path": node.path,
        "metadata_confirmed": True,
    }


def ensure_intake_workflow(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
    user: account_models.User,
) -> dm.DocumentWorkflowInstance:
    """Create the draft lifecycle together with controlled-document intake.

    Registering controlled documented information and starting its lifecycle are
    one business transaction.  Leaving the workflow absent made a successfully
    uploaded document look uncontrolled and required a second, easy-to-miss API
    action before review could begin.
    """
    existing = db.query(dm.DocumentWorkflowInstance).filter(
        dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
        dm.DocumentWorkflowInstance.revision_id == revision.id,
    ).first()
    if existing is not None:
        return existing

    profile = _profile(db, tenant=tenant, manual=manual)
    open_changes = db.query(dm.DocumentChangeRequest).filter(
        dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
        dm.DocumentChangeRequest.manual_id == manual.id,
        dm.DocumentChangeRequest.status.in_({"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}),
        or_(
            dm.DocumentChangeRequest.revision_id.is_(None),
            dm.DocumentChangeRequest.revision_id == revision.id,
        ),
    ).all()
    links = db.query(dm.DocumentIntegrationLink).filter(
        dm.DocumentIntegrationLink.tenant_id == tenant.amo_id,
        dm.DocumentIntegrationLink.manual_id == manual.id,
        or_(
            dm.DocumentIntegrationLink.revision_id.is_(None),
            dm.DocumentIntegrationLink.revision_id == revision.id,
        ),
    ).all()
    linked_modules = {str(link.source_module or "").upper() for link in links}
    training_required = bool(
        any(change.training_impact_required for change in open_changes)
        or linked_modules.intersection({"TRAINING", "TRAINING_AND_COMPETENCE"})
    )
    qms_required = bool(
        any(change.qms_blocking for change in open_changes)
        or linked_modules.intersection({"QMS", "QUALITY", "QUALITY_AND_COMPLIANCE"})
    )
    workflow = dm.DocumentWorkflowInstance(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        state="DRAFT",
        requires_authority=bool(profile.requires_authority_approval or profile.regulated_flag),
        training_impact_required=training_required,
        training_readiness_status="PENDING" if training_required else "NOT_REQUIRED",
        qms_readiness_status="PENDING" if qms_required else "NOT_REQUIRED",
        distribution_readiness_status="PENDING" if profile.acknowledgement_required else "NOT_REQUIRED",
        created_by_user_id=user.id,
    )
    db.add(workflow)
    db.flush()
    from .workflow_notifications import notify_workflow_progress

    notify_workflow_progress(db, tenant=tenant, manual=manual, workflow=workflow)
    return workflow
