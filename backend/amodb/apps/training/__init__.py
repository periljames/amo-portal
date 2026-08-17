"""Training domain package."""

# Import the router once, then replace only its evidence transfer and training
# record presentation call targets. This preserves the established FastAPI
# route/dependency contracts while centralising public/PDF record semantics.
from . import compliance as _training_compliance
from . import router as _router_module
from .record_presentation import explicit_recurrence_key, install_training_record_presentation
from .shared_storage_policy import install_training_shared_storage

install_training_shared_storage(_router_module)
install_training_record_presentation(_router_module)

# Legacy compliance code used title/code suffix stripping to infer Initial ↔
# Recurrent families. Keep the existing evaluator, but make its family identity
# explicit-only: group_code, declared prerequisite, otherwise the course itself.
_training_compliance._course_family_key = lambda course: explicit_recurrence_key(course)

__all__ = ["install_training_record_presentation", "install_training_shared_storage"]
