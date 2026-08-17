"""Training domain package."""

# Import the router once, then replace only its evidence transfer and training
# record presentation call targets. This preserves the established FastAPI
# route/dependency contracts while centralising public/PDF record semantics.
from . import compliance as _training_compliance
from . import course_lifecycle as _course_lifecycle
from . import router as _router_module
from .record_presentation import install_training_record_presentation
from .shared_storage_policy import install_training_shared_storage
from .workflow_completion import install_training_workflow_completion

install_training_shared_storage(_router_module)
install_training_record_presentation(_router_module)
install_training_workflow_completion(_router_module)

# Compatibility boundary for legacy compliance internals. Runtime relationship
# identity now comes only from explicit catalogue fields; no title/code parsing.
_training_compliance._course_family_key = lambda course: _course_lifecycle.explicit_recurrence_key(course)
_training_compliance.is_initial_course = _course_lifecycle.is_initial_course
_training_compliance.is_refresher_course = _course_lifecycle.is_recurrent_course

__all__ = [
    "install_training_record_presentation",
    "install_training_shared_storage",
    "install_training_workflow_completion",
]
