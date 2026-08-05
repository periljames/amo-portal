"""Compatibility-free domain export for the universal induction bounded context.

All ORM definitions live in ``domain_models``. Keeping this single import surface
prevents duplicate SQLAlchemy table registration while allowing conventional
``from . import models`` usage inside the module.
"""

from .domain_models import *  # noqa: F401,F403
