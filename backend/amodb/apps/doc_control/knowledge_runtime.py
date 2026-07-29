"""Bind the exact-page indexer to the public knowledge-service contract.

The first hierarchy implementation exposed the indexing callables from
``knowledge_service``. Keep that import contract stable for routers and workers
while the page-native PDF implementation lives in ``knowledge_indexer``.
"""
from __future__ import annotations

from . import knowledge_indexer, knowledge_service


knowledge_service.index_revision_references = knowledge_indexer.index_revision_references
knowledge_service.index_revision_background = knowledge_indexer.index_revision_background


__all__ = []
