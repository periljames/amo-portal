# backend/amodb/__init__.py
"""
Import ORM models from each app so that:

- Alembic (later) and Base.metadata.create_all() see all tables.
- The package exposes a clear surface.

The actual model classes are kept in amodb/apps/*/models.py.
"""

from .apps.accounts import models as accounts_models          # AMO / users / auth
from .apps.fleet import models as fleet_models                # aircraft + components
from .apps.work import models as work_models                  # work orders + tasks
from .apps.crs import models as crs_models                    # CRS + signoffs
from .apps.maintenance_program import models as maintenance_program_models  # AMP + aircraft program items

__all__ = [
    "accounts_models",
    "fleet_models",
    "work_models",
    "crs_models",
    "maintenance_program_models",
]
