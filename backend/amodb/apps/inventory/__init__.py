"""Inventory and supply-chain router registration."""

from .router import router
from . import models
from amodb.apps.procurement import supplier_governance_models as _supplier_governance_models  # noqa: F401
from amodb.apps.procurement.supplier_governance_router import router as supplier_governance_router
from amodb.apps.procurement.router import router as procurement_router
from amodb.apps.procurement.document_router import router as procurement_document_router

# Governed supplier endpoints are mounted before the legacy Procurement router.
# The overlapping supplier scope/decision paths therefore fail closed through
# the evaluation workflow for browser and direct API clients alike.
router.include_router(supplier_governance_router)
router.include_router(procurement_router)
router.include_router(procurement_document_router)
