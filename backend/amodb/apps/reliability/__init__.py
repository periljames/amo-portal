"""Reliability module package."""

from . import models  # noqa: E402,F401
from . import advanced_models  # noqa: E402,F401
from . import formal_reporting_models  # noqa: E402,F401
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
from . import workbook_parity  # noqa: E402,F401
from . import workbook_parity_contract_hardening  # noqa: E402,F401
from . import workbook_daily_contract_hardening  # noqa: E402,F401
from . import workbook_parity_defaults  # noqa: E402,F401
from . import workbook_reference_hardening  # noqa: E402,F401
from . import workbook_authority_hardening  # noqa: E402,F401
from . import workbook_parity_imports  # noqa: E402,F401
from . import structured_csv_import  # noqa: E402,F401
from . import workbook_reference_import  # noqa: E402,F401
from . import workbook_parity_statistics  # noqa: E402,F401
from . import workbook_analysis_integrity  # noqa: E402,F401
from . import workbook_revision_hardening  # noqa: E402,F401
from . import management_reporting  # noqa: E402,F401
from . import management_reporting_enrichment  # noqa: E402,F401
from . import formal_reporting  # noqa: E402,F401
from . import formal_reporting_render  # noqa: E402,F401
from . import formal_reporting_governance  # noqa: E402,F401
from . import formal_reporting_history  # noqa: E402,F401
from . import formal_reporting_source_capture  # noqa: E402,F401
from . import formal_reporting_snapshot_guard  # noqa: E402,F401
from . import formal_reporting_supersession  # noqa: E402,F401
from . import formal_reporting_publication_hardening  # noqa: E402,F401
from . import workbook_rbac_hardening  # noqa: E402,F401

workpack_integration.register(router)
operational_hardening.apply(operational_sources)
operational_sources.activate_authoritative_adapters(authoritative_adapters)
operational_hardening.finalize(operational_sources)
operational_sources.register(router)
analytics_dashboard.register(router)
workbook_parity.register(router)
workbook_parity_defaults.register(router)
# Governed routes register before legacy compatibility routes so exact workbook-
# reference and source-audit contracts are authoritative.
workbook_reference_import.register(router)
workbook_parity_imports.register(router)
structured_csv_import.register(router)
workbook_analysis_integrity.register(router)
workbook_parity_statistics.register(router)
workbook_revision_hardening.register(router)
management_reporting_enrichment.apply(management_reporting)
management_reporting.register(router)
formal_reporting_source_capture.apply()
formal_reporting_snapshot_guard.apply()
formal_reporting_supersession.apply()
formal_reporting_publication_hardening.apply()
formal_reporting.register(router)
formal_reporting_render.register(router)
formal_reporting_governance.register(router)
formal_reporting_history.register(router)
workbook_rbac_hardening.apply(router)
