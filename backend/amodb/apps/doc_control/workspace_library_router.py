from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import governance_models as gm
from . import knowledge_models as km
from .governance_service import effective_assignments, serialize_assignment
from .workspace_service import (
    is_control_user,
    resolve_tenant,
    role_value,
    serialize_manual,
    serialize_workflow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Library"])
OPEN_CHANGE_STATUSES = {"OPEN", "ASSESSING", "ACCEPTED", "IMPLEMENTING"}
CONTENT_NODE_TYPES = {
    "MANUAL",
    "POLICY",
    "PROCEDURE",
    "WORK_INSTRUCTION",
    "FORM",
    "CHECKLIST",
    "REGISTER",
    "EXTERNAL_DOCUMENT",
}
UNRESOLVED_ASSIGNMENTS = {"DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"}
UNRESOLVED_RELATIONSHIPS = {"DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"}
UNRESOLVED_REFERENCES = {"UNRESOLVED", "AMBIGUOUS", "BROKEN", "OUTDATED", "AUTO_RESOLVED"}


def _user_labels(db: Session, ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    return {
        row.id: {"id": row.id, "name": row.full_name, "email": row.email}
        for row in db.query(account_models.User).filter(account_models.User.id.in_(ids)).all()
    }


def _department_labels(db: Session, ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    return {
        row.id: {"id": row.id, "code": row.code, "name": row.name}
        for row in db.query(account_models.Department).filter(account_models.Department.id.in_(ids)).all()
    }


def _physical_summary(rows: list[dm.DocumentControlledCopy]) -> dict[str, dict[str, int]]:
    today = datetime.utcnow().date()
    result: dict[str, dict[str, int]] = defaultdict(lambda: {
        "total": 0,
        "on_shelf": 0,
        "checked_out": 0,
        "recalled": 0,
        "overdue": 0,
    })
    for row in rows:
        bucket = result[row.manual_id]
        if row.status == "DESTROYED":
            continue
        bucket["total"] += 1
        if row.status == "RETURNED" and not row.holder_user_id:
            bucket["on_shelf"] += 1
        if row.holder_user_id and row.status in {"ISSUED", "RECALLED"}:
            bucket["checked_out"] += 1
        if row.status == "RECALLED":
            bucket["recalled"] += 1
        if (
            row.due_back_at
            and row.status in {"ISSUED", "RECALLED"}
            and row.due_back_at.date() < today
        ):
            bucket["overdue"] += 1
    return result


def _scope_match(scope_column, key: str, expected: str, *, case_insensitive: bool = False):
    """Return a correlated PostgreSQL JSONB-array membership predicate.

    Access scopes are legacy JSON payloads and are not guaranteed to have
    normalized role/department case. Expanding the relevant array in SQL keeps
    permission filtering semantically aligned with ``can_read_manual`` while
    allowing count/offset/limit to remain database-bounded.
    """
    values = func.jsonb_array_elements_text(
        func.coalesce(scope_column[key], func.jsonb_build_array())
    ).table_valued("value").alias(f"scope_{key}")
    candidate = func.upper(values.c.value) if case_insensitive else values.c.value
    target = expected.upper() if case_insensitive else expected
    return select(1).select_from(values).where(candidate == target).exists()


def _page_read_target(
    manual: manual_models.Manual,
    *,
    controller: bool,
    revisions_by_id: dict[str, manual_models.ManualRevision],
    latest_by_manual: dict[str, manual_models.ManualRevision],
) -> tuple[manual_models.ManualRevision | None, str]:
    """Resolve a library-row read target from the already bulk-loaded page data.

    This intentionally mirrors ``workspace_service.readable_revision`` without
    issuing one or more revision queries for every result row.  The canonical
    reader still validates the target independently when opened.
    """
    if manual.current_published_rev_id:
        published = revisions_by_id.get(manual.current_published_rev_id)
        if (
            published
            and published.manual_id == manual.id
            and published.status_enum == manual_models.ManualRevisionStatus.PUBLISHED
        ):
            return published, "PUBLISHED"
    if controller:
        latest = latest_by_manual.get(manual.id)
        if latest:
            return latest, "UNCONTROLLED"
    return None, "NONE"


@router.get("/t/{tenant_slug}/documents", include_in_schema=False)
def list_visible_documents(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    document_class: str | None = None,
    status: str | None = None,
    node_type: str | None = Query(default=None, max_length=48),
    owner_user_id: str | None = Query(default=None, max_length=36),
    department_id: str | None = Query(default=None, max_length=36),
    indexing_status: str | None = Query(default=None, max_length=32),
    unresolved_ownership: bool = False,
    unresolved_relationships: bool = False,
    structure_status: str | None = Query(default=None, max_length=32),
    superseded_referenced: bool = False,
    sort: str = Query(default="code", pattern="^(code|title|type|status)$"),
    direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return the access-filtered company library, not merely a manual register.

    Access predicates, total counting and pagination execute in PostgreSQL before
    document rows are materialized. This prevents restricted records from
    influencing disclosed counts and keeps result work bounded for large tenants.
    """
    tenant = resolve_tenant(db, tenant_slug, current_user)
    controller = is_control_user(current_user)
    query = (
        db.query(manual_models.Manual, dm.DocumentControlProfile)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant.amo_id),
        )
        .filter(manual_models.Manual.tenant_id == tenant.id)
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        matching_revision = exists().where(and_(
            manual_models.ManualRevision.manual_id == manual_models.Manual.id,
            manual_models.ManualRevision.source_filename.ilike(needle),
        ))
        matching_node = exists().where(and_(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id == manual_models.Manual.id,
            or_(km.DocumentationNode.code.ilike(needle), km.DocumentationNode.title.ilike(needle)),
        ))
        query = query.filter(or_(
            manual_models.Manual.code.ilike(needle),
            manual_models.Manual.title.ilike(needle),
            manual_models.Manual.manual_type.ilike(needle),
            matching_revision,
            matching_node,
        ))
    if status:
        query = query.filter(manual_models.Manual.status == status)
    if document_class:
        query = query.filter(
            func.coalesce(dm.DocumentControlProfile.document_class, "INTERNAL")
            == document_class.strip().upper()
        )
    if node_type:
        requested = node_type.strip().upper()
        if requested in CONTENT_NODE_TYPES:
            query = query.filter(exists().where(and_(
                km.DocumentationNode.tenant_id == tenant.amo_id,
                km.DocumentationNode.manual_id == manual_models.Manual.id,
                km.DocumentationNode.node_type == requested,
                km.DocumentationNode.status == "ACTIVE",
            )))
    if owner_user_id or department_id or unresolved_ownership:
        responsibility_conditions = [
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.manual_id == manual_models.Manual.id,
            gm.DocumentResponsibilityAssignment.responsibility_type.in_(["DOCUMENT_OWNER", "BUSINESS_OWNER", "RESPONSIBLE_DEPARTMENT"]),
        ]
        if owner_user_id:
            responsibility_conditions.append(gm.DocumentResponsibilityAssignment.assignee_user_id == owner_user_id)
        if department_id:
            responsibility_conditions.append(gm.DocumentResponsibilityAssignment.assignee_department_id == department_id)
        if unresolved_ownership:
            responsibility_conditions.append(gm.DocumentResponsibilityAssignment.confirmation_status.in_(UNRESOLVED_ASSIGNMENTS))
        query = query.filter(exists().where(and_(*responsibility_conditions)))
    if indexing_status:
        query = query.filter(exists().where(and_(
            km.DocumentationIndexJob.tenant_id == tenant.amo_id,
            km.DocumentationIndexJob.manual_id == manual_models.Manual.id,
            km.DocumentationIndexJob.status == indexing_status.strip().upper(),
        )))
    if unresolved_relationships:
        unresolved_reference = exists().where(and_(
            km.DocumentationReference.tenant_id == tenant.amo_id,
            km.DocumentationReference.source_manual_id == manual_models.Manual.id,
            km.DocumentationReference.status.in_(UNRESOLVED_REFERENCES),
        ))
        unresolved_relationship = exists().where(and_(
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            gm.DocumentGovernedRelationship.source_manual_id == manual_models.Manual.id,
            gm.DocumentGovernedRelationship.resolution_status.in_(UNRESOLVED_RELATIONSHIPS),
        ))
        query = query.filter(or_(unresolved_reference, unresolved_relationship))
    if str(structure_status or "").upper() == "ORPHANED":
        query = query.filter(exists().where(and_(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id == manual_models.Manual.id,
            km.DocumentationNode.parent_id.is_(None),
            km.DocumentationNode.node_type != "ROOT",
        )))
    if superseded_referenced:
        target_revision = manual_models.ManualRevision.__table__.alias("library_target_revision")
        query = query.filter(exists().where(and_(
            km.DocumentationReference.tenant_id == tenant.amo_id,
            km.DocumentationReference.source_manual_id == manual_models.Manual.id,
            km.DocumentationReference.status == "VERIFIED",
            km.DocumentationReference.target_revision_id == target_revision.c.id,
            target_revision.c.status_enum == manual_models.ManualRevisionStatus.SUPERSEDED,
        )))

    if not controller:
        profile = dm.DocumentControlProfile
        access_conditions = [
            profile.id.is_(None),
            profile.restricted_flag.is_(False),
            _scope_match(profile.access_scope_json, "user_ids", str(current_user.id)),
        ]
        user_role = role_value(current_user)
        if user_role:
            access_conditions.append(
                _scope_match(profile.access_scope_json, "roles", user_role, case_insensitive=True)
            )
        department_code = getattr(getattr(current_user, "department", None), "code", None)
        if department_code:
            access_conditions.append(
                _scope_match(
                    profile.access_scope_json,
                    "departments",
                    str(department_code),
                    case_insensitive=True,
                )
            )
        query = query.filter(or_(*access_conditions))

    sort_map = {
        "code": manual_models.Manual.code,
        "title": manual_models.Manual.title,
        "type": manual_models.Manual.manual_type,
        "status": manual_models.Manual.status,
    }
    sort_column = sort_map[sort]
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()

    visible_id_subquery = query.with_entities(
        manual_models.Manual.id.label("manual_id")
    ).subquery()
    facet_counter = dict(
        db.query(
            km.DocumentationNode.node_type,
            func.count(func.distinct(km.DocumentationNode.manual_id)),
        )
        .join(
            visible_id_subquery,
            visible_id_subquery.c.manual_id == km.DocumentationNode.manual_id,
        )
        .filter(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.status == "ACTIVE",
            km.DocumentationNode.node_type.in_(CONTENT_NODE_TYPES),
        )
        .group_by(km.DocumentationNode.node_type)
        .all()
    )

    total = query.count()
    selected = (
        query.order_by(ordering, manual_models.Manual.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    manuals = [manual for manual, _profile in selected]
    profiles = {manual.id: profile for manual, profile in selected}
    manual_ids = [manual.id for manual in manuals]

    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id.in_(manual_ids or ["-"]))
        .order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc())
        .all()
    )
    latest_by_manual: dict[str, manual_models.ManualRevision] = {}
    revisions_by_id: dict[str, manual_models.ManualRevision] = {}
    for revision in revisions:
        latest_by_manual.setdefault(revision.manual_id, revision)
        revisions_by_id[revision.id] = revision

    visible_nodes = (
        db.query(km.DocumentationNode)
        .filter(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id.in_(manual_ids or ["-"]),
            km.DocumentationNode.status == "ACTIVE",
        )
        .all()
    )
    nodes = {row.manual_id: row for row in visible_nodes}
    copies = (
        db.query(dm.DocumentControlledCopy)
        .filter(
            dm.DocumentControlledCopy.tenant_id == tenant.amo_id,
            dm.DocumentControlledCopy.manual_id.in_(manual_ids or ["-"]),
        )
        .all()
    )
    physical = _physical_summary(copies)

    external_sources = {
        row.manual_id: row
        for row in db.query(dm.ExternalDocumentSource)
        .filter(
            dm.ExternalDocumentSource.tenant_id == tenant.amo_id,
            dm.ExternalDocumentSource.manual_id.in_(manual_ids or ["-"]),
        )
        .all()
    }
    source_ids = [row.id for row in external_sources.values()]
    receipts = (
        db.query(dm.ExternalRevisionReceipt)
        .filter(
            dm.ExternalRevisionReceipt.tenant_id == tenant.amo_id,
            dm.ExternalRevisionReceipt.source_id.in_(source_ids or ["-"]),
        )
        .order_by(dm.ExternalRevisionReceipt.received_at.desc(), dm.ExternalRevisionReceipt.id.desc())
        .all()
    )
    latest_receipt: dict[str, dm.ExternalRevisionReceipt] = {}
    for receipt in receipts:
        latest_receipt.setdefault(receipt.source_id, receipt)

    assignments = (
        db.query(gm.DocumentResponsibilityAssignment)
        .filter(
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.manual_id.in_(manual_ids or ["-"]),
        )
        .all()
    )
    assignments_by_manual: dict[str, list[gm.DocumentResponsibilityAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_manual[assignment.manual_id].append(assignment)
    users = _user_labels(db, {row.assignee_user_id for row in assignments if row.assignee_user_id})
    departments = _department_labels(db, {row.assignee_department_id for row in assignments if row.assignee_department_id})

    if controller:
        workflows = {
            row.revision_id: row
            for row in db.query(dm.DocumentWorkflowInstance)
            .filter(
                dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
                dm.DocumentWorkflowInstance.manual_id.in_(manual_ids or ["-"]),
            )
            .all()
        }
        open_change_counts = dict(db.query(
            dm.DocumentChangeRequest.manual_id, func.count(dm.DocumentChangeRequest.id),
        ).filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.manual_id.in_(manual_ids or ["-"]),
            dm.DocumentChangeRequest.status.in_(OPEN_CHANGE_STATUSES),
        ).group_by(dm.DocumentChangeRequest.manual_id).all())
        pending_ack_counts = dict(db.query(
            dm.DocumentDistributionCampaign.manual_id,
            func.count(dm.DocumentDistributionRecipient.id),
        ).join(
            dm.DocumentDistributionRecipient,
            dm.DocumentDistributionRecipient.campaign_id == dm.DocumentDistributionCampaign.id,
        ).filter(
            dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id,
            dm.DocumentDistributionCampaign.manual_id.in_(manual_ids or ["-"]),
            dm.DocumentDistributionRecipient.status == "PENDING",
        ).group_by(dm.DocumentDistributionCampaign.manual_id).all())
        semantic_counts = dict(db.query(
            gm.DocumentGovernedRelationship.source_manual_id,
            func.count(gm.DocumentGovernedRelationship.id),
        ).filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
            gm.DocumentGovernedRelationship.source_manual_id.in_(manual_ids or ["-"]),
            gm.DocumentGovernedRelationship.resolution_status == "CONFIRMED",
        ).group_by(gm.DocumentGovernedRelationship.source_manual_id).all())
        integration_rows = (
            db.query(dm.DocumentIntegrationLink)
            .filter(
                dm.DocumentIntegrationLink.tenant_id == tenant.amo_id,
                dm.DocumentIntegrationLink.manual_id.in_(manual_ids or ["-"]),
            )
            .all()
        )
        integrations: dict[str, dict] = defaultdict(lambda: {"count": 0, "modules": set(), "blocking": 0})
        for row in integration_rows:
            integrations[row.manual_id]["count"] += 1
            integrations[row.manual_id]["modules"].add(row.source_module)
            if row.blocking:
                integrations[row.manual_id]["blocking"] += 1
        record_counts = dict(db.query(
            km.DocumentationRecord.template_manual_id,
            func.count(km.DocumentationRecord.id),
        ).filter(
            km.DocumentationRecord.tenant_id == tenant.amo_id,
            km.DocumentationRecord.template_manual_id.in_(manual_ids or ["-"]),
        ).group_by(km.DocumentationRecord.template_manual_id).all())
    else:
        workflows = {}
        open_change_counts = {}
        pending_ack_counts = {}
        semantic_counts = {}
        integrations = {}
        record_counts = {}

    items: list[dict] = []
    for manual in manuals:
        profile = profiles.get(manual.id)
        target, target_kind = _page_read_target(
            manual,
            controller=controller,
            revisions_by_id=revisions_by_id,
            latest_by_manual=latest_by_manual,
        )
        latest = latest_by_manual.get(manual.id) if controller else target
        payload = serialize_manual(manual, profile, target, target_kind, latest)
        node = nodes.get(manual.id)
        payload["library"] = {
            "node_type": node.node_type if node else "MANUAL",
            "structure_path": node.path if node else None,
            "physical": physical.get(manual.id, {"total": 0, "on_shelf": 0, "checked_out": 0, "recalled": 0, "overdue": 0}),
            "external": None,
            "semantic_relationships": int(semantic_counts.get(manual.id, 0)) if controller else None,
            "integrations": None,
            "generated_records": int(record_counts.get(manual.id, 0)) if controller else None,
        }
        source = external_sources.get(manual.id)
        if source:
            receipt = latest_receipt.get(source.id)
            payload["library"]["external"] = {
                "provider": source.provider,
                "authority": source.authority,
                "status": source.status,
                "next_check_due_at": source.next_check_due_at.isoformat() if source.next_check_due_at else None,
                "revision_label": receipt.revision_label if receipt else None,
                "currency_status": receipt.currency_status if receipt else "UNVERIFIED",
                "applicability_status": receipt.applicability_status if receipt else "PENDING",
            }
        active = effective_assignments(assignments_by_manual.get(manual.id, []))
        owner = (active.get("DOCUMENT_OWNER") or active.get("BUSINESS_OWNER") or [None])[0]
        responsible = (active.get("RESPONSIBLE_DEPARTMENT") or [None])[0]
        payload["library"]["owner"] = serialize_assignment(owner, users=users, departments=departments) if owner else None
        payload["library"]["responsible_department"] = serialize_assignment(responsible, users=users, departments=departments) if responsible else None

        if not controller:
            profile_payload = payload.get("profile")
            if isinstance(profile_payload, dict):
                profile_payload["access_scope"] = {}
                profile_payload["metadata"] = {}
            payload["workflow"] = None
            payload["open_change_requests"] = 0
            payload["pending_acknowledgements"] = 0
        else:
            workflow = workflows.get(latest.id) if latest else None
            payload["workflow"] = serialize_workflow(workflow) if workflow else None
            payload["open_change_requests"] = int(open_change_counts.get(manual.id, 0))
            payload["pending_acknowledgements"] = int(pending_ack_counts.get(manual.id, 0))
            integration = integrations.get(manual.id)
            payload["library"]["integrations"] = {
                "count": int(integration["count"]) if integration else 0,
                "modules": sorted(integration["modules"]) if integration else [],
                "blocking": int(integration["blocking"]) if integration else 0,
            }
        items.append(payload)

    return {
        "items": items,
        "facets": {
            "node_types": {key: int(facet_counter.get(key, 0)) for key in sorted(CONTENT_NODE_TYPES)},
            "visible_documents": total,
        },
        "capabilities": {"read": True, "control": controller},
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(items)},
    }
