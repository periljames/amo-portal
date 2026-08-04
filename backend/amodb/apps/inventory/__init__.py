"""Inventory and supply-chain router registration."""

from .router import router
from . import models
from amodb.apps.procurement.router import router as procurement_router
from amodb.apps.procurement.document_router import router as procurement_document_router

router.include_router(procurement_router)
router.include_router(procurement_document_router)
