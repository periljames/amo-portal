"""Workforce test mapper bootstrap.

Workforce work-pattern models reference Rostering shift templates by class name.
Import the Rostering model module before tests configure or compile ORM queries so
SQLAlchemy has the complete shared mapper registry.
"""
from amodb.apps.rostering import models as rostering_models  # noqa: F401
