# backend/amodb/__init__.py

from . import models as core_models  # users, archived users, etc.
from .apps.fleet import models as fleet_models
from .apps.work import models as work_models
from .apps.crs import models as crs_models

__all__ = [
    "core_models",
    "fleet_models",
    "work_models",
    "crs_models",
]
