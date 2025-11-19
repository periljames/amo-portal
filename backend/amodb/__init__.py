# backend/amodb/__init__.py
from .database import Base, engine, SessionLocal  # noqa: F401

# Core models (User, etc.)
from . import models  # noqa: F401

# CRS app models
from .apps.crs import models as crs_models  # noqa: F401
