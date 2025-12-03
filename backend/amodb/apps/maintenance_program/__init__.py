# backend/amodb/apps/maintenance_program/__init__.py
"""
Maintenance program app package.

We only expose models/schemas/services here so that:
- Alembic can see the ORM models via amodb.__init__
- The main FastAPI app can import router directly from .api

Do NOT import .api here to avoid circular imports when Alembic loads env.py.
"""

from . import models, schemas, services  # noqa: F401

__all__ = [
    "models",
    "schemas",
    "services",
]
