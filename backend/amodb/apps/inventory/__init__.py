"""
Inventory module.

Handles stock ledger, purchasing flows, and traceability for parts. The canonical
Procurement department router is mounted here so the application entrypoint keeps
one inventory/supply-chain registration point while Procurement remains its own
domain package.
"""

from .router import router  # noqa: F401
from . import models  # noqa: F401
from amodb.apps.procurement.router import router as procurement_router

router.include_router(procurement_router)
