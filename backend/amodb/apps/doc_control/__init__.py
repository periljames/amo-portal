"""Document Control application package.

Model-only imports are used by Alembic, indexing workers, and Publications reader
services. Loading the HTTP router at package import time creates avoidable circular
imports between Manuals and Document Control, so the router is exposed lazily.
"""
from __future__ import annotations

import sitecustomize  # noqa: F401  # process-gated Alembic compatibility hook


def __getattr__(name: str):
    if name == "router":
        from .router import router
        return router
    raise AttributeError(name)


__all__ = ["router"]
