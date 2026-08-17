"""Training domain package."""

# Import the router once, then replace only its evidence transfer and training
# record presentation call targets. This preserves the established FastAPI
# route/dependency contracts while centralising public/PDF record semantics.
from . import router as _router_module
from .record_presentation import install_training_record_presentation
from .shared_storage_policy import install_training_shared_storage

install_training_shared_storage(_router_module)
install_training_record_presentation(_router_module)

__all__ = ["install_training_record_presentation", "install_training_shared_storage"]
