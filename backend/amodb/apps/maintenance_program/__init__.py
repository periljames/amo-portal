# backend/amodb/apps/maintenance_program/__init__.py
"""
Maintenance program module (AMP + per-aircraft program items).

NOTE:
We intentionally only import models and schemas at package import time.
Importing services here can cause circular import issues during Alembic's
metadata loading, and services are not needed for migrations.
"""

from . import models, schemas  # noqa: F401
