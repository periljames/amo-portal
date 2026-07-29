"""Bind optimized knowledge-graph runtime implementations.

The stable service contract remains in ``knowledge_service`` while exact PDF
indexing and one-time form capability discovery are installed here before the
HTTP routers import those callables.
"""
from __future__ import annotations

from . import knowledge_indexer, knowledge_models, knowledge_service


knowledge_service.index_revision_references = knowledge_indexer.index_revision_references
knowledge_service.index_revision_background = knowledge_indexer.index_revision_background

_original_ensure_execution_profile = knowledge_service._ensure_execution_profile


def _ensure_execution_profile_once(
    db,
    *,
    tenant_id: str,
    manual,
    node_type: str,
    record_series,
    actor_id: str | None,
):
    row = (
        db.query(knowledge_models.DocumentationExecutionProfile)
        .filter(
            knowledge_models.DocumentationExecutionProfile.tenant_id == tenant_id,
            knowledge_models.DocumentationExecutionProfile.manual_id == manual.id,
        )
        .first()
    )
    if row:
        if not row.record_series_node_id:
            row.record_series_node_id = record_series.id
        return row
    return _original_ensure_execution_profile(
        db,
        tenant_id=tenant_id,
        manual=manual,
        node_type=node_type,
        record_series=record_series,
        actor_id=actor_id,
    )


knowledge_service._ensure_execution_profile = _ensure_execution_profile_once


__all__ = []
