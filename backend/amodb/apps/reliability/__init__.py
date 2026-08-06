"""Reliability module package."""

from .router import router  # noqa: F401
from . import models  # noqa: E402,F401
from . import advanced_models  # noqa: E402,F401
from . import workpack_integration  # noqa: E402,F401
from . import authoritative_adapters  # noqa: E402,F401
from . import operational_sources  # noqa: E402,F401
from . import operational_hardening  # noqa: E402,F401
from . import workbook_parity  # noqa: E402,F401
from . import workbook_parity_defaults  # noqa: E402,F401
from . import workbook_parity_statistics  # noqa: E402,F401

workpack_integration.register(router)
operational_hardening.apply(operational_sources)
operational_sources.activate_authoritative_adapters(authoritative_adapters)
operational_hardening.finalize(operational_sources)
operational_sources.register(router)
workbook_parity.register(router)
workbook_parity_defaults.register(router)
workbook_parity_statistics.register(router)
