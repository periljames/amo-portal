"""Duty rostering and workforce integration module.

The application historically imports ``amodb.apps.rostering.router`` directly.
Load the concrete rostering route module once, construct the aggregate router,
and then expose that aggregate under the historical submodule key. This keeps
``amodb.main`` unchanged while mounting canonical sibling route prefixes
``/rostering`` and ``/workforce``.
"""
from __future__ import annotations

import sys

from ..accounts import router_modules_admin as _module_admin
from . import application_router as _application_router

_module_admin.ALLOWED_MODULES.update({"rostering", "workforce"})
sys.modules[f"{__name__}.router"] = _application_router
router = _application_router

__all__ = ["router"]
