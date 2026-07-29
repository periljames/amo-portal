"""Preserve stable identity for governed manual-less hierarchy nodes."""
from __future__ import annotations

from . import knowledge_hardening, knowledge_models, knowledge_service


_original_ensure_node = knowledge_service._ensure_node


def _select_stable_manual_less_node(candidates, *, node_type: str, metadata: dict | None):
    """Resolve generated nodes through stable governed metadata, not mutable code."""
    if node_type != "RECORD_SERIES":
        return None
    template_manual_id = str((metadata or {}).get("template_manual_id") or "")
    if not template_manual_id:
        return None
    for row in candidates:
        row_metadata = dict(getattr(row, "metadata_json", None) or {})
        if (
            getattr(row, "manual_id", None) is None
            and str(row_metadata.get("template_manual_id") or "") == template_manual_id
        ):
            return row
    return None


def _ensure_node_with_stable_manual_less_identity(
    db,
    *,
    tenant_id: str,
    code: str,
    title: str,
    node_type: str,
    parent,
    manual_id: str | None = None,
    order_index: int = 0,
    metadata: dict | None = None,
    actor_id: str | None = None,
):
    if manual_id is None and node_type == "RECORD_SERIES":
        candidates = (
            db.query(knowledge_models.DocumentationNode)
            .filter(
                knowledge_models.DocumentationNode.tenant_id == tenant_id,
                knowledge_models.DocumentationNode.manual_id.is_(None),
                knowledge_models.DocumentationNode.node_type == node_type,
            )
            .all()
        )
        stable = _select_stable_manual_less_node(
            candidates,
            node_type=node_type,
            metadata=metadata,
        )
        if stable and knowledge_service.normalize_code(stable.code) != knowledge_service.normalize_code(code):
            # A code mismatch on the same stable record-series relationship means a
            # controller renamed the node. Preserve that governed identity instead of
            # allocating a second generated series during immediate reconciliation.
            stable.metadata_json = {
                **dict(stable.metadata_json or {}),
                **dict(metadata or {}),
                "hierarchy_management": "GOVERNED",
            }
            return stable

    return _original_ensure_node(
        db,
        tenant_id=tenant_id,
        code=code,
        title=title,
        node_type=node_type,
        parent=parent,
        manual_id=manual_id,
        order_index=order_index,
        metadata=metadata,
        actor_id=actor_id,
    )


knowledge_service._ensure_node = _ensure_node_with_stable_manual_less_identity


__all__ = ["_select_stable_manual_less_node"]
