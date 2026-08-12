from __future__ import annotations

from fastapi import APIRouter, Depends

# Bind hardened knowledge-graph implementations before route modules copy service
# callables into their module namespaces.
from . import knowledge_runtime as _knowledge_runtime  # noqa: F401
from .governance_router import router as governance_router
from .governance_runtime_guard import install as install_governance_runtime_guard
from .reader_governance_router import router as reader_governance_router
from .knowledge_access_router import workspace_tree_router
from .knowledge_resolution_router import router as knowledge_resolution_router
from .router_legacy import router as legacy_router
from .knowledge_assistant_router import router as knowledge_assistant_router
from .knowledge_assistant_runtime_guard import install as install_knowledge_assistant_runtime_guard
from .knowledge_records_router import router as knowledge_records_router
from .knowledge_workspace_router import router as knowledge_workspace_router
from .reminder_lifecycle_router import router as reminder_lifecycle_router
from .workspace_access import enforce_workspace_access
from .workspace_administration_router import router as workspace_administration_router
from .workspace_applicability_router import router as workspace_applicability_router
from .workspace_authority_router import router as workspace_authority_router
from .workspace_change_router import router as workspace_change_router
from .workspace_compliance_portfolio_router import router as workspace_compliance_portfolio_router
from .workspace_copy_evidence_router import router as workspace_copy_evidence_router
from .workspace_copy_incident_router import router as workspace_copy_incident_router
from .workspace_copy_router import router as workspace_copy_router
from .workspace_dashboard_router import router as workspace_dashboard_router
from .workspace_distribution_portfolio_router import router as workspace_distribution_portfolio_router
from .workspace_distribution_router import router as workspace_distribution_router
from .workspace_document_lifecycle_router import router as workspace_document_lifecycle_router
from .workspace_evidence_router import router as workspace_evidence_router
from .workspace_external_assessment_router import router as workspace_external_assessment_router
from .workspace_external_router import router as workspace_external_router
from .workspace_integration_router import router as workspace_integration_router
from .workspace_library_discovery_router import router as workspace_library_discovery_router
from .workspace_library_router import router as workspace_library_router
from .workspace_portfolio_router import router as workspace_portfolio_router
from .workspace_profile_router import router as workspace_profile_router
from .workspace_record_router import router as workspace_record_router
from .workspace_reports_export_router import router as workspace_reports_export_router
from .workspace_reports_portfolio_router import router as workspace_reports_portfolio_router
from .workspace_reports_register_router import router as workspace_reports_register_router
from .workspace_reports_router import router as workspace_reports_router
from .workspace_review_router import router as workspace_review_router
from .workspace_router import router as workspace_router
from .workspace_tr_router import router as workspace_tr_router
from .workspace_tr_terminal_router import router as workspace_tr_terminal_router
from .workspace_workflow_authority_router import router as workspace_workflow_authority_router
from .workspace_workflow_create_router import router as workspace_workflow_create_router
from .workspace_workflow_review_router import router as workspace_workflow_review_router
from .workspace_workflow_router import router as workspace_workflow_router


install_knowledge_assistant_runtime_guard()
install_governance_runtime_guard()

router = APIRouter()
router.include_router(reminder_lifecycle_router)
router.include_router(legacy_router)
# These narrow overrides preserve existing endpoint contracts while correcting
# access filtering, pagination, reader/controller payload separation, source-module
# verification, controlled change assessment, verified applicability, authority
# evidence, controlled-copy custody/incidents, distribution integrity,
# external-source currency/assessment, periodic-review follow-up, profile-owner
# tenancy, terminal temporary-revision immutability, accountable approval authority,
# decision evidence, active-recipient publication, server-derived workflow impact,
# governed hierarchy/reference integrity, generated record custody,
# permission-filtered assisted search, bounded library discovery, bounded operating
# portfolios, bounded evidence registers/exports, immutable evidence attachments,
# governed reminders/escalations, administration, document lifecycle controls, and
# release safeguards.
# They must precede the compatibility workspace router because Starlette resolves
# matching routes in declaration order.
router.include_router(workspace_dashboard_router, prefix="/doc-control")
router.include_router(workspace_portfolio_router, prefix="/doc-control")
router.include_router(workspace_distribution_portfolio_router, prefix="/doc-control")
router.include_router(workspace_compliance_portfolio_router, prefix="/doc-control")
router.include_router(workspace_reports_portfolio_router, prefix="/doc-control")
router.include_router(workspace_reports_register_router, prefix="/doc-control")
router.include_router(workspace_reports_export_router, prefix="/doc-control")
router.include_router(workspace_administration_router, prefix="/doc-control")
router.include_router(workspace_external_assessment_router, prefix="/doc-control")
router.include_router(workspace_copy_incident_router, prefix="/doc-control")
router.include_router(workspace_library_discovery_router, prefix="/doc-control")
router.include_router(workspace_library_router, prefix="/doc-control")
router.include_router(workspace_record_router, prefix="/doc-control")
router.include_router(
    governance_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    reader_governance_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_tree_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    knowledge_resolution_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    knowledge_workspace_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    knowledge_assistant_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    knowledge_records_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_profile_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_integration_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_evidence_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_change_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_applicability_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_authority_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_copy_evidence_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_copy_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_distribution_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_external_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_review_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_tr_terminal_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_tr_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_workflow_create_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_workflow_review_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_workflow_authority_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_workflow_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_document_lifecycle_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_reports_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)