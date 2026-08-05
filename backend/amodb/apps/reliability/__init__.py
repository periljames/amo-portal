"""Reliability module package."""

from .router import router  # noqa: F401
from . import models  # noqa: E402,F401
from . import advanced_models  # noqa: E402,F401
from . import workpack_integration  # noqa: E402,F401
from . import authoritative_adapters  # noqa: E402,F401

workpack_integration.register(router)
authoritative_adapters.register(router)
