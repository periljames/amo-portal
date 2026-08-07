"""Source-backed reusable aircraft content packs."""

# Install the hardened OEM governance implementations before importing routers.
# Existing public route contracts therefore use the same controlled write path
# as the richer backend governance API rather than leaving a weaker legacy path.
from . import services as services
from . import governance as governance

governance.install(services)

from .router import router

__all__ = ["router"]
