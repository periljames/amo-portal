"""Training domain package."""

# Import the router once, then replace only its evidence transfer call targets.
# This preserves the established FastAPI route/dependency contracts while making
# retained Training evidence replica-safe.
from . import router as _router_module
from .shared_storage_policy import install_training_shared_storage

install_training_shared_storage(_router_module)

__all__ = ["install_training_shared_storage"]
