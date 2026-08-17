"""Read-only serialization of the existing documented-information hierarchy."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from . import domain_models
from . import governance_models as gm
from . import knowledge_models as km
from .knowledge_hardening import _filter_hierarchy_items
from .knowledge_service import serialize_execution_profile
from .workspace_service import can_read_manual, is_control_user


def read_only_hierarchy_payload(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    user: account_models.User,
) -> dict:
    """Return persisted hierarchy state without reconciliation or writes."""
    tenant_id = str(manual_tenant.amo_id)
    nodes = (
        db.query(km.DocumentationNode)
        .filter(
            km.DocumentationNode.tenant_id == tenant_id,
            km.DocumentationNode.status == "ACTIVE",
        )
        .order_by(
            km.DocumentationNode.depth.asc(),
            km.DocumentationNode.order_index.asc(),
            km.DocumentationNode.title.asc(),
        )
        .all()
    )
    manual_ids = {str(node.manual_id) for node in nodes if node.manual_id}
    manuals = {
        str(row.id): row
        for row in db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.tenant_id == manual_tenant.id,
            manual_models.Manual.id.in_(manual_ids or {"-"}),
        )
        .all()
    }
    control_profiles = {
        str(row.manual_id): row
        for row in db.query(domain_models.DocumentControlProfile)
        .filter(domain_models.DocumentControlProfile.tenant_id == tenant_id)
        .all()
    }
    if is_control_user(user):
        readable_manual_ids = set(manuals)
    else:
        readable_manual_ids = {
            manual_id
            for manual_id in manuals
            if can_read_manual(user, control_profiles.get(manual_id))
        }

    visibility_items = [
        {
            "id": node.id,
            "parent_id": node.parent_id,
            "manual_id": node.manual_id,
            "metadata": dict(node.metadata_json or {}),
        }
        for node in nodes
    ]
    visible_ids = {
        str(item["id"])
        for item in _filter_hierarchy_items(visibility_items, readable_manual_ids)
    }
    visible_manual_ids = {
        str(node.manual_id)
        for node in nodes
        if str(node.id) in visible_ids and node.manual_id
    }
    execution_profiles = {
        str(row.manual_id): row
        for row in db.query(km.DocumentationExecutionProfile)
        .filter(
            km.DocumentationExecutionProfile.tenant_id == tenant_id,
            km.DocumentationExecutionProfile.manual_id.in_(visible_manual_ids or {"-"}),
        )
        .all()
    }
    latest_revisions: dict[str, manual_models.ManualRevision] = {}
    for revision in (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id.in_(visible_manual_ids or {"-"}))
        .order_by(
            manual_models.ManualRevision.manual_id.asc(),
            manual_models.ManualRevision.created_at.desc(),
            manual_models.ManualRevision.id.desc(),
        )
        .all()
    ):
        latest_revisions.setdefault(str(revision.manual_id), revision)

    items: list[dict] = []
    for node in nodes:
        if str(node.id) not in visible_ids:
            continue
        manual = manuals.get(str(node.manual_id)) if node.manual_id else None
        latest = latest_revisions.get(str(manual.id)) if manual else None
        execution = execution_profiles.get(str(node.manual_id)) if node.manual_id else None
        items.append(
            {
                "id": node.id,
                "parent_id": node.parent_id,
                "node_type": node.node_type,
                "code": node.code,
                "title": node.title,
                "path": node.path,
                "depth": node.depth,
                "order_index": node.order_index,
                "manual_id": node.manual_id,
                "status": node.status,
                "metadata": dict(node.metadata_json or {}),
                "document": {
                    "manual_type": manual.manual_type,
                    "status": manual.status,
                    "current_published_revision_id": manual.current_published_rev_id,
                    "latest_revision_id": latest.id if latest else None,
                    "latest_revision": latest.rev_number if latest else None,
                    "source_type": (
                        str(
                            getattr(
                                getattr(latest, "source_type_enum", None),
                                "value",
                                getattr(latest, "source_type_enum", ""),
                            )
                        )
                        if latest
                        else None
                    ),
                }
                if manual
                else None,
                "execution": serialize_execution_profile(execution) if execution else None,
            }
        )

    counts: dict[str, int] = {}
    if is_control_user(user):
        aggregated = defaultdict(int)
        for row in (
            db.query(km.DocumentationReference.status)
            .filter(km.DocumentationReference.tenant_id == tenant_id)
            .all()
        ):
            aggregated[str(row[0])] += 1
        counts = dict(aggregated)

    return {
        "tenant_id": manual_tenant.amo_id,
        "root_id": next((item["id"] for item in items if item["node_type"] == "ROOT"), None),
        "items": items,
        "reference_health": counts,
    }


def _related_edge(row, *, direction: str, related_node: dict) -> dict:
    return {
        "id": row.id,
        "kind": "GOVERNED_RELATIONSHIP",
        "direction": direction,
        "relationship_type": row.relationship_type,
        "relationship_source": row.relationship_source,
        "status": row.resolution_status,
        "source_manual_id": row.source_manual_id,
        "target_manual_id": row.target_manual_id,
        "related_node": related_node,
        "exact_token": row.exact_token,
        "exact_quote": row.exact_quote,
        "page_number": row.page_number,
        "section_label": row.section_label,
        "confidence_percent": row.confidence_percent,
    }


def _reference_edge(row, *, direction: str, related_node: dict) -> dict:
    return {
        "id": row.id,
        "kind": "DETECTED_REFERENCE",
        "direction": direction,
        "relationship_type": row.relationship_type,
        "status": row.status,
        "source_manual_id": row.source_manual_id,
        "target_manual_id": row.target_manual_id,
        "related_node": related_node,
        "raw_token": row.raw_token,
        "source_quote": row.source_quote,
        "source_page_number": row.source_page_number,
        "confidence_percent": row.confidence_percent,
    }


def read_only_node_connections(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    user: account_models.User,
    node_id: str,
) -> dict | None:
    """Return the visible lineage around one hierarchy node without mutation."""
    hierarchy = read_only_hierarchy_payload(db, manual_tenant=manual_tenant, user=user)
    items = hierarchy["items"]
    by_id = {str(item["id"]): item for item in items}
    selected = by_id.get(str(node_id))
    if selected is None:
        return None

    by_manual_id = {
        str(item["manual_id"]): item
        for item in items
        if item.get("manual_id")
    }
    visible_manual_ids = set(by_manual_id)
    breadcrumbs: list[dict] = []
    cursor = selected
    visited: set[str] = set()
    while cursor and str(cursor["id"]) not in visited:
        visited.add(str(cursor["id"]))
        breadcrumbs.append(cursor)
        cursor = by_id.get(str(cursor.get("parent_id"))) if cursor.get("parent_id") else None
    breadcrumbs.reverse()
    children_by_parent: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        children_by_parent[str(item.get("parent_id") or "")].append(item)
    children = sorted(
        children_by_parent.get(str(selected["id"]), []),
        key=lambda item: (item["order_index"], item["title"]),
    )

    governed_edges: list[dict] = []
    detected_edges: list[dict] = []
    manual_id = str(selected.get("manual_id") or "")
    if manual_id:
        relationships = (
            db.query(gm.DocumentGovernedRelationship)
            .filter(
                gm.DocumentGovernedRelationship.tenant_id == manual_tenant.amo_id,
                or_(
                    and_(
                        gm.DocumentGovernedRelationship.source_manual_id == manual_id,
                        gm.DocumentGovernedRelationship.target_manual_id.in_(visible_manual_ids or {"-"}),
                    ),
                    and_(
                        gm.DocumentGovernedRelationship.target_manual_id == manual_id,
                        gm.DocumentGovernedRelationship.source_manual_id.in_(visible_manual_ids or {"-"}),
                    ),
                ),
            )
            .order_by(
                gm.DocumentGovernedRelationship.updated_at.desc(),
                gm.DocumentGovernedRelationship.id.desc(),
            )
            .limit(250)
            .all()
        )
        for row in relationships:
            outgoing = str(row.source_manual_id) == manual_id
            related_manual_id = str(row.target_manual_id or "") if outgoing else str(row.source_manual_id)
            related_node = by_manual_id.get(related_manual_id)
            if related_node is None or related_manual_id not in visible_manual_ids:
                continue
            governed_edges.append(
                _related_edge(row, direction="OUTGOING" if outgoing else "INCOMING", related_node=related_node)
            )

        references = (
            db.query(km.DocumentationReference)
            .filter(
                km.DocumentationReference.tenant_id == manual_tenant.amo_id,
                or_(
                    and_(
                        km.DocumentationReference.source_manual_id == manual_id,
                        km.DocumentationReference.target_manual_id.in_(visible_manual_ids or {"-"}),
                    ),
                    and_(
                        km.DocumentationReference.target_manual_id == manual_id,
                        km.DocumentationReference.source_manual_id.in_(visible_manual_ids or {"-"}),
                    ),
                ),
            )
            .order_by(km.DocumentationReference.updated_at.desc(), km.DocumentationReference.id.desc())
            .limit(250)
            .all()
        )
        for row in references:
            outgoing = str(row.source_manual_id) == manual_id
            related_manual_id = str(row.target_manual_id or "") if outgoing else str(row.source_manual_id)
            related_node = by_manual_id.get(related_manual_id)
            if related_node is None or related_manual_id not in visible_manual_ids:
                continue
            detected_edges.append(
                _reference_edge(row, direction="OUTGOING" if outgoing else "INCOMING", related_node=related_node)
            )

    record_sources = [
        item
        for item in items
        if item.get("manual_id")
        and (item.get("execution") or {}).get("record_series_node_id") == selected["id"]
    ]
    record_series = None
    execution = selected.get("execution") or {}
    if execution.get("record_series_node_id"):
        record_series = by_id.get(str(execution["record_series_node_id"]))

    workflow_types = {"FORM", "CHECKLIST", "REGISTER", "RECORD_SERIES"}
    descendant_ids: set[str] = set()
    # Follow the selected hierarchy branch and the branches rooted at directly
    # related documents. This lets a manual expose forms nested under a related
    # procedure without requiring users to discover the chain one click at a
    # time.
    frontier = list(dict.fromkeys([
        str(selected["id"]),
        *(str(edge["related_node"]["id"]) for edge in [*governed_edges, *detected_edges]),
    ]))
    expanded: set[str] = set()
    while frontier:
        parent_id = frontier.pop()
        if parent_id in expanded:
            continue
        expanded.add(parent_id)
        nested = [
            item
            for item in children_by_parent.get(parent_id, [])
            if str(item["id"]) not in descendant_ids
        ]
        descendant_ids.update(str(item["id"]) for item in nested)
        frontier.extend(str(item["id"]) for item in nested)

    workflow_candidates = [
        item
        for item in items
        if str(item["id"]) in descendant_ids
        and item.get("node_type") in workflow_types
    ]
    workflow_candidates.extend(record_sources)
    if record_series:
        workflow_candidates.append(record_series)
    for edge in [*governed_edges, *detected_edges]:
        related_node = edge["related_node"]
        if related_node.get("node_type") in workflow_types:
            workflow_candidates.append(related_node)

    # A form is only half of the lineage. Include its configured output series
    # even when the form is connected by a governed link rather than nesting.
    for item in list(workflow_candidates):
        series_id = (item.get("execution") or {}).get("record_series_node_id")
        series_node = by_id.get(str(series_id)) if series_id else None
        if series_node:
            workflow_candidates.append(series_node)
    workflow_nodes = list(
        {str(item["id"]): item for item in workflow_candidates}.values()
    )[:100]

    record_template_ids = {
        str(item["manual_id"])
        for item in workflow_nodes
        if item.get("manual_id")
        and item.get("node_type") in {"FORM", "CHECKLIST", "REGISTER"}
    }
    if manual_id:
        record_template_ids.add(manual_id)
    record_series_ids = {
        str(item["id"])
        for item in workflow_nodes
        if item.get("node_type") == "RECORD_SERIES"
    }
    if selected.get("node_type") == "RECORD_SERIES":
        record_series_ids.add(str(selected["id"]))

    record_filters = []
    if record_template_ids:
        record_filters.append(
            km.DocumentationRecord.template_manual_id.in_(record_template_ids)
        )
    if record_series_ids:
        record_filters.append(
            km.DocumentationRecord.record_series_node_id.in_(record_series_ids)
        )
    record_filter = or_(*record_filters) if record_filters else None

    records: list[dict] = []
    record_total = 0
    records_scope = "ALL" if is_control_user(user) else "OWN"
    if record_filter is not None:
        record_query = db.query(km.DocumentationRecord).filter(
            km.DocumentationRecord.tenant_id == manual_tenant.amo_id,
            record_filter,
        )
        if not is_control_user(user):
            record_query = record_query.filter(km.DocumentationRecord.submitted_by_user_id == user.id)
        record_total = int(record_query.count())
        rows = (
            record_query.order_by(
                km.DocumentationRecord.submitted_at.desc(),
                km.DocumentationRecord.id.desc(),
            )
            .limit(25)
            .all()
        )
        for row in rows:
            template = by_manual_id.get(str(row.template_manual_id))
            records.append(
                {
                    "id": row.id,
                    "record_number": row.record_number,
                    "status": row.status,
                    "artifact_filename": row.artifact_filename,
                    "template_manual_id": row.template_manual_id,
                    "template": {
                        "code": template["code"],
                        "title": template["title"],
                    }
                    if template
                    else None,
                    "record_series_node_id": row.record_series_node_id,
                    "submitted_by_user_id": row.submitted_by_user_id,
                    "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
                    "retention_years": row.retention_years,
                    "download_url": f"/manuals/t/{manual_tenant.slug}/records/{row.id}/artifact.pdf",
                }
            )

    return {
        "tenant_id": manual_tenant.amo_id,
        "node": selected,
        "breadcrumbs": breadcrumbs,
        "children": children,
        "record_series": record_series,
        "record_sources": record_sources,
        "workflow_nodes": workflow_nodes,
        "governed_relationships": governed_edges,
        "detected_references": detected_edges,
        "records": {
            "items": records,
            "total": record_total,
            "scope": records_scope,
            "limit": 25,
        },
        "capabilities": {
            "read": True,
            "control": is_control_user(user),
            "records_scope": records_scope,
        },
    }


__all__ = ["read_only_hierarchy_payload", "read_only_node_connections"]
