"""Install hardened Document Control knowledge-graph runtime bindings.

This module is imported before the knowledge routers bind service callables.
"""
from __future__ import annotations

from . import knowledge_hardening as _knowledge_hardening  # noqa: F401
from . import knowledge_hierarchy_identity as _knowledge_hierarchy_identity  # noqa: F401
from . import knowledge_path_integrity as _knowledge_path_integrity  # noqa: F401
from . import knowledge_signature_guard as _knowledge_signature_guard  # noqa: F401
from . import knowledge_artifact_transactions as _knowledge_artifact_transactions  # noqa: F401


__all__ = []
