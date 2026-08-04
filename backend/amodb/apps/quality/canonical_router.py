"""Canonical Quality API composition.

The established QMS endpoints remain in ``canonical_router_legacy`` while the
modern planning surface is isolated in ``planner_router``. Keeping composition in
this module preserves every existing import path used by the application.
"""

from .canonical_router_legacy import *  # noqa: F401,F403
from .canonical_router_legacy import core_router, legacy_router, router
from .planner_router import planner_router

# ``canonical_router_legacy`` already copied ``core_router`` into the public and
# legacy path routers during import. Include the planner on all three explicitly so
# direct core-router users and both URL families receive the same planner contract.
core_router.include_router(planner_router)
router.include_router(planner_router)
legacy_router.include_router(planner_router)
