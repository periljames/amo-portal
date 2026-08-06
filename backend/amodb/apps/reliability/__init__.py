"""Reliability module package."""

from . import models  # noqa: E402,F401
from . import advanced_models  # noqa: E402,F401
from . import formula_hardening  # noqa: E402,F401
from . import analytics_threshold_hardening  # noqa: E402,F401
from . import advanced_schemas  # noqa: E402,F401
from . import formula_schema_hardening  # noqa: E402,F401
from .router import router  # noqa: E402,F401
from . import workpack_integration  # noqa: E402,F401
from . import authoritative_adapters  # noqa: E402,F401
from . import operational_sources  # noqa: E402,F401
from . import operational_hardening  # noqa: E402,F401
from . import analytics_dashboard  # noqa: E402,F401

workpack_integration.register(router)
operational_hardening.apply(operational_sources)
operational_sources.activate_authoritative_adapters(authoritative_adapters)
operational_hardening.finalize(operational_sources)
operational_sources.register(router)
analytics_dashboard.register(router)
