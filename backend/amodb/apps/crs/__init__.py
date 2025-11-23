# backend/amodb/apps/crs/__init__.py

"""
CRS (Certificate of Release to Service) app.

This module is imported in amodb.__init__ so that Alembic sees the models.
"""

from . import models  # noqa: F401
