# backend/amodb/apps/workforce/router_entry.py
"""Hardened application entrypoint for the workforce router.

The generated route module uses SQLAlchemy's ``selectinload`` in endpoint
queries.  Import and inject it here before the router is registered so the
module remains executable while preserving the route file as the single API
contract source.
"""
from sqlalchemy.orm import selectinload

from . import router as router_module

router_module.selectinload = selectinload
router = router_module.router

__all__ = ["router"]
