"""Source-backed reusable aircraft content packs."""

# Install the hardened OEM governance implementations before importing routers.
# Existing public route contracts therefore use the same controlled write path
# as the richer backend governance API rather than leaving a weaker legacy path.
from . import services as services
from . import governance as governance
from . import backend_hardening as backend_hardening
from . import backend_ingestion_hardening as backend_ingestion_hardening
from . import backend_services as backend_services
from . import backend_materialization_hardening as backend_materialization_hardening
from . import backend_currentness_hardening as backend_currentness_hardening

governance.install(services)
backend_hardening.install(governance, services)
backend_ingestion_hardening.install()
backend_materialization_hardening.install(backend_services)
backend_currentness_hardening.install()

from .router import router

__all__ = ["router"]
