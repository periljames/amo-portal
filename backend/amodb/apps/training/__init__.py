"""Training domain package."""

# Import the router once, then install bounded extensions onto the canonical
# Training API. This preserves established FastAPI route/dependency contracts
# while avoiding a parallel LMS or duplicate domain roots.
from . import compliance as _training_compliance
from . import course_lifecycle as _course_lifecycle
from . import governance_service as _governance_service
from . import operating_service as _operating_service
from . import router as _router_module
from .assessment_readiness_bridge import bridge_readiness as _bridge_assessment_readiness
from .calendar_lifecycle import install_training_calendar_lifecycle
from .canonical_assessment_routes import install_training_canonical_assessment_routes
from .canonical_exam_governance_routes import install_training_canonical_exam_governance_routes
from .governance_course_scope import technical_authorisation_readiness as _revision_aware_technical_readiness
from .governance_routes import install_training_governance_routes
from .learner_invitation_routes import install_training_learner_invitation_routes
from .learner_workflow_routes import install_training_learner_workflow_routes
from .notification_dispatch_routes import install_training_notification_dispatch_routes
from .record_presentation import install_training_record_presentation
from .shared_storage_policy import install_training_shared_storage
from .tenant_report_control import install_tenant_report_control
from .workflow_completion_installer import install_training_workflow_completion_without_legacy_assessment_routes

# Governed routes may receive a TrainingCourseRevision.id while existing technical
# authorisations remain scoped to canonical TrainingCourse.id. Keep that compatibility
# boundary in one place rather than changing legacy authorisation identities.
_governance_service.technical_authorisation_readiness = _revision_aware_technical_readiness

# The original readiness calculator recognizes the legacy APPROVED/PASS state
# vocabulary. Canonical assessment attempts use COMPLETED/PASSED. Bridge those
# vocabularies at the single readiness boundary without creating a second case model.
_operating_service.compute_authorization_readiness = _bridge_assessment_readiness(
    _operating_service.compute_authorization_readiness
)

# Cross-cutting controls are installed before route extensions so every Training
# write uses the same tenant-owned report metadata and calendar lifecycle.
install_tenant_report_control(_router_module)
install_training_calendar_lifecycle()

install_training_shared_storage(_router_module)
install_training_record_presentation(_router_module)
install_training_workflow_completion_without_legacy_assessment_routes(_router_module)
install_training_canonical_assessment_routes(_router_module)
install_training_learner_invitation_routes(_router_module)
install_training_learner_workflow_routes(_router_module)
install_training_notification_dispatch_routes(_router_module)
install_training_governance_routes(_router_module)
install_training_canonical_exam_governance_routes(_router_module)

# Compatibility boundary for legacy compliance internals. Runtime relationship
# identity now comes only from explicit catalogue fields; no title/code parsing.
_training_compliance._course_family_key = lambda course: _course_lifecycle.explicit_recurrence_key(course)
_training_compliance.is_initial_course = _course_lifecycle.is_initial_course
_training_compliance.is_refresher_course = _course_lifecycle.is_recurrent_course

__all__ = [
    "install_training_calendar_lifecycle",
    "install_training_canonical_assessment_routes",
    "install_training_canonical_exam_governance_routes",
    "install_training_governance_routes",
    "install_training_learner_invitation_routes",
    "install_training_learner_workflow_routes",
    "install_training_notification_dispatch_routes",
    "install_training_record_presentation",
    "install_training_shared_storage",
    "install_tenant_report_control",
    "install_training_workflow_completion_without_legacy_assessment_routes",
]
