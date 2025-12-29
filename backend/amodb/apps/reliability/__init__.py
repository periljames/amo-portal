# backend/amodb/apps/reliability/__init__.py
"""
Reliability module.

Provides reliability analytics, recurring findings and recommendations
derived from fleet utilisation and maintenance program execution.
"""

from .router import router  # noqa: F401
from . import models  # noqa: F401
