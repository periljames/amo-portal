"""Realtime package.

Keep package import side-effect free so tooling (e.g. Alembic model import)
does not require runtime-only dependencies.
"""

__all__: list[str] = []
