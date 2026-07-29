"""Read-only serialization of the existing documented-information hierarchy."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from . import domain_models
from . import knowledge_models as km
from .knowledge_hardening import _filter_hierarchy_items
from .knowledge_service import serialize_execution_profile
from .workspace_service import can_read_manual, is_control_user


def _latest_revision(db: Session, manual_id: str) -> manual_models.ManualRevision | None:
    return (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual_id)
        .order_by(
            manual_models.ManualRevision.created_at.desc(),
            manual_models.ManualRevision.id.desc(),
        )
        .first()
    )


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

    items: list[dict] = []
    for node in nodes:
        if str(node.id) not in visible_ids:
            continue
        manual = manuals.get(str(node.manual_id)) if node.manual_id else None
        latest = _latest_revision(db, manual.id) if manual else None
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


__all__ = ["read_only_hierarchy_payload"]
