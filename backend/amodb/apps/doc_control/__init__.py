"""Document Control application package.

Model-only imports are used by Alembic, indexing workers, and Publications reader
services. Loading the HTTP router at package import time creates avoidable circular
imports between Manuals and Document Control, so the router is exposed lazily.
"""
from __future__ import annotations

import sitecustomize  # noqa: F401  # process-gated Alembic compatibility hook

# Ensure normalized governance, reader-evidence, and retained DMS evidence tables
# participate in SQLAlchemy/Alembic metadata without eagerly importing the HTTP
# routing graph.
from . import evidence_models as _evidence_models  # noqa: F401
from . import governance_models as _governance_models  # noqa: F401
from . import reader_governance_models as _reader_governance_models  # noqa: F401


def __getattr__(name: str):
    if name == "router":
        from .router import router
        return router
    raise AttributeError(name)


__all__ = ["router"]
