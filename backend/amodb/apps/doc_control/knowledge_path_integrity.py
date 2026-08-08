"""Enforce persisted hierarchy path integrity at the database boundary.

The documented-information hierarchy stores a materialized path for bounded tree
reads and governed move validation. ``documentation_nodes.path`` is deliberately
NOT NULL, so every insertion path must have identity and hierarchy coordinates
before SQL is emitted. This mapper hook is a final invariant guard for service,
seed, migration-support and future creation callers.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import event, select

from .knowledge_models import DocumentationNode


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-").lower()
    return segment[:120] or "node"


def _compose_node_path(
    *,
    parent_path: str | None,
    parent_depth: int | None,
    node_id: str,
    code: str,
) -> tuple[str, int]:
    segment = f"{_safe_segment(code)}~{node_id[:8]}"
    if not parent_path:
        return f"/{segment}", 0
    return f"{parent_path.rstrip('/')}/{segment}", int(parent_depth or 0) + 1


@event.listens_for(DocumentationNode, "before_insert", propagate=True)
def _ensure_documentation_node_path_before_insert(_mapper, connection, target: DocumentationNode) -> None:
    """Populate identity/path before PostgreSQL enforces the NOT NULL contract."""
    if not target.id:
        target.id = str(uuid.uuid4())

    if target.path:
        if target.depth is None:
            target.depth = max(0, target.path.rstrip("/").count("/") - 1)
        return

    parent_path: str | None = None
    parent_depth: int | None = None
    if target.parent_id:
        parent = connection.execute(
            select(DocumentationNode.path, DocumentationNode.depth).where(
                DocumentationNode.id == target.parent_id,
                DocumentationNode.tenant_id == target.tenant_id,
            )
        ).one_or_none()
        if not parent or not parent[0]:
            raise ValueError("Documentation hierarchy parent must exist with a materialized path before child insertion")
        parent_path = str(parent[0])
        parent_depth = int(parent[1] or 0)

    target.path, target.depth = _compose_node_path(
        parent_path=parent_path,
        parent_depth=parent_depth,
        node_id=str(target.id),
        code=str(target.code or "node"),
    )


__all__ = ["_compose_node_path"]
