"""Additive governed Training Operating System routes.

Installed onto the canonical /training router so this is not a second LMS or API
root.  All parent lookups are tenant scoped before mutation.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import governance_models as models
from . import governance_rules as rules
from . import governance_schemas as schemas
from . import governance_service as service
from . import models as legacy_models
from .permissions import TrainingCapability as Cap, require_not_self_approval, require_training_capability, tenant_id_for


def install_training_governance_routes(router_module) -> None:
    router = router_module.router
    if getattr(router_module, "_training_governance_routes_installed", False):
        return
    router_module._training_governance_routes_installed = True

    @router.get("/operating/governance/authorities", response_model=list[schemas.AuthorityRead])
    def list_authorities(
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
    ):
        return db.query(models.TrainingAuthority).filter(models.TrainingAuthority.amo_id == tenant_id_for(current_user)).order_by(models.TrainingAuthority.code).all()

    @router.post("/operating/governance/authorities", response_model=schemas.AuthorityRead, status_code=201)
    def create_authority(
        payload: schemas.AuthorityCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = models.TrainingAuthority(amo_id=amo_id, created_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/rules", response_model=schemas.RuleSetRead)
    def governed_rules(
        on_date: date = Query(default_factory=date.today),
        rule_code: str | None = None,
        course_id: str | None = None,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
    ):
        context = {"course_id": course_id} if course_id else {}
        rows, conflicts = service.list_effective_rules(db, amo_id=tenant_id_for(current_user), on_date=on_date, context=context, rule_code=rule_code)
        if conflicts:
            service.persist_conflicts(db, amo_id=tenant_id_for(current_user), conflicts=conflicts, context=context)
            db.commit()
        return {"rules": rows, "conflicts": conflicts, "status": "CONFLICT" if conflicts else "CLEAR"}

    @router.post("/operating/governance/rules", response_model=schemas.GovernanceRuleRead, status_code=201)
    def create_governance_rule(
        payload: schemas.GovernanceRuleCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        if payload.authority_id:
            service._tenant_row(db, models.TrainingAuthority, amo_id=amo_id, row_id=payload.authority_id, label="Training authority")
        row = models.TrainingGovernanceRule(amo_id=amo_id, created_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/conflicts")
    def list_governance_conflicts(
        conflict_status: str = "OPEN",
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
    ):
        rows = db.query(models.TrainingGovernanceConflict).filter(
            models.TrainingGovernanceConflict.amo_id == tenant_id_for(current_user),
            models.TrainingGovernanceConflict.status == conflict_status.upper(),
        ).order_by(models.TrainingGovernanceConflict.created_at.desc()).limit(limit).all()
        return [service._dict(row) for row in rows]

    @router.post("/operating/governance/conflicts/{conflict_id}/resolve")
    def resolve_governance_conflict(
        conflict_id: str,
        payload: schemas.GovernanceConflictResolution,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        conflict = service._tenant_row(db, models.TrainingGovernanceConflict, amo_id=amo_id, row_id=conflict_id, label="Governance conflict")
        resolved_rule = service._tenant_row(db, models.TrainingGovernanceRule, amo_id=amo_id, row_id=payload.resolved_rule_id, label="Governance rule")
        if str(resolved_rule.id) not in {str(value) for value in conflict.rule_ids or []}:
            raise HTTPException(status_code=409, detail="The selected rule is not a member of this conflict set.")
        conflict.status = "RESOLVED"
        conflict.resolution = payload.resolution
        conflict.resolved_rule_id = resolved_rule.id
        conflict.resolved_by_user_id = str(current_user.id)
        conflict.resolved_at = service._utcnow()
        db.commit(); db.refresh(conflict)
        return service._dict(conflict)

    @router.get("/operating/governance/approvals", response_model=list[schemas.ApprovalRead])
    def list_approvals(
        approval_type: str | None = None,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
    ):
        query = db.query(models.TrainingApproval).filter(models.TrainingApproval.amo_id == tenant_id_for(current_user))
        if approval_type:
            query = query.filter(models.TrainingApproval.approval_type == approval_type.upper())
        return query.order_by(models.TrainingApproval.expiry_date.asc().nullslast(), models.TrainingApproval.approval_number).all()

    @router.post("/operating/governance/approvals", response_model=schemas.ApprovalRead, status_code=201)
    def create_approval(
        payload: schemas.ApprovalCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingAuthority, amo_id=amo_id, row_id=payload.authority_id, label="Training authority")
        row = models.TrainingApproval(amo_id=amo_id, created_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/approvals/{approval_id}/scopes", status_code=201)
    def create_approval_scope(
        approval_id: str,
        payload: schemas.ApprovalScopeCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=approval_id, label="Training approval")
        row = models.TrainingApprovalScope(amo_id=amo_id, approval_id=approval_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/approvals/{approval_id}/transition", response_model=schemas.ApprovalRead)
    def transition_approval(
        approval_id: str,
        payload: schemas.ApprovalTransition,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=approval_id, label="Training approval")
        if payload.status == "ACTIVE":
            if not (row.supporting_dms_revision_id or row.authority_correspondence_id):
                raise HTTPException(status_code=409, detail="Approval cannot become ACTIVE without controlled authority evidence.")
            require_not_self_approval(actor_user_id=str(current_user.id), originator_user_id=row.created_by_user_id, action="activate")
            row.verified_by_user_id = str(current_user.id)
            row.verified_at = service._utcnow()
        row.status = payload.status
        db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/technical-authorisations", response_model=list[schemas.TechnicalAuthorisationRead])
    def list_technical_authorisations(
        user_id: str | None = None,
        privilege_type: str | None = None,
        auth_status: str | None = None,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_VIEW)),
    ):
        query = db.query(models.TrainingTechnicalAuthorisation).filter(models.TrainingTechnicalAuthorisation.amo_id == tenant_id_for(current_user))
        if user_id:
            query = query.filter(models.TrainingTechnicalAuthorisation.user_id == user_id)
        if privilege_type:
            query = query.filter(models.TrainingTechnicalAuthorisation.privilege_type == privilege_type.upper())
        if auth_status:
            query = query.filter(models.TrainingTechnicalAuthorisation.status == auth_status.upper())
        return query.order_by(models.TrainingTechnicalAuthorisation.expiry_date.asc().nullslast()).all()

    @router.post("/operating/governance/technical-authorisations", response_model=schemas.TechnicalAuthorisationRead, status_code=201)
    def create_technical_authorisation(
        payload: schemas.TechnicalAuthorisationCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_PREPARE)),
    ):
        amo_id = tenant_id_for(current_user)
        person = db.query(account_models.User).filter(account_models.User.id == payload.user_id, account_models.User.amo_id == amo_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person was not found in this tenant.")
        if payload.authority_id:
            service._tenant_row(db, models.TrainingAuthority, amo_id=amo_id, row_id=payload.authority_id, label="Training authority")
        if payload.approval_id:
            service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=payload.approval_id, label="Training approval")
        row = models.TrainingTechnicalAuthorisation(amo_id=amo_id, issued_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/technical-authorisations/{authorisation_id}/transition", response_model=schemas.TechnicalAuthorisationRead)
    def transition_technical_authorisation(
        authorisation_id: str,
        payload: schemas.TechnicalAuthorisationTransition,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.AUTHORIZATION_ISSUE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = service._tenant_row(db, models.TrainingTechnicalAuthorisation, amo_id=amo_id, row_id=authorisation_id, label="Technical authorisation")
        if payload.status == "ACTIVE":
            require_not_self_approval(actor_user_id=str(current_user.id), originator_user_id=row.issued_by_user_id, action="approve")
            if not row.evidence_json:
                raise HTTPException(status_code=409, detail="Technical authorisation requires controlled qualification evidence before activation.")
            row.approved_by_user_id = str(current_user.id)
        elif payload.status == "SUSPENDED":
            row.suspended_reason = payload.reason
        elif payload.status == "REVOKED":
            row.revoked_reason = payload.reason
        row.status = payload.status
        db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/technical-authorisations/{user_id}/readiness", response_model=schemas.TechnicalReadinessRead)
    def technical_authorisation_readiness(
        user_id: str,
        privilege_type: str,
        on_date: date,
        course_id: str | None = None,
        aircraft: str | None = None,
        theory: bool = False,
        practical: bool = False,
        ojt: bool = False,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_VIEW)),
    ):
        return service.technical_authorisation_readiness(
            db, amo_id=tenant_id_for(current_user), user_id=user_id, privilege_type=privilege_type,
            on_date=on_date, course_id=course_id, aircraft=aircraft, require_theory=theory,
            require_practical=practical, require_ojt=ojt,
        )

    @router.get("/operating/governance/course-revisions", response_model=list[schemas.CourseRevisionRead])
    def list_course_revisions(
        course_id: str | None = None,
        revision_status: str | None = None,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_VIEW)),
    ):
        query = db.query(models.TrainingCourseRevision).filter(models.TrainingCourseRevision.amo_id == tenant_id_for(current_user))
        if course_id:
            query = query.filter(models.TrainingCourseRevision.course_id == course_id)
        if revision_status:
            query = query.filter(models.TrainingCourseRevision.status == revision_status.upper())
        return query.order_by(models.TrainingCourseRevision.course_id, models.TrainingCourseRevision.revision_no.desc()).all()

    @router.post("/operating/governance/course-revisions", response_model=schemas.CourseRevisionRead, status_code=201)
    def create_course_revision(
        payload: schemas.CourseRevisionCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        course = db.query(legacy_models.TrainingCourse).filter(legacy_models.TrainingCourse.id == payload.course_id, legacy_models.TrainingCourse.amo_id == amo_id).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course was not found in this tenant.")
        if payload.authority_id:
            service._tenant_row(db, models.TrainingAuthority, amo_id=amo_id, row_id=payload.authority_id, label="Training authority")
        if payload.course_approval_id:
            service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=payload.course_approval_id, label="Course approval")
        row = models.TrainingCourseRevision(amo_id=amo_id, created_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/course-revisions/{revision_id}/modules", status_code=201)
    def create_course_module(
        revision_id: str,
        payload: schemas.CourseModuleCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
        row = models.TrainingCourseModule(amo_id=amo_id, course_revision_id=revision_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/modules/{module_id}/objectives", status_code=201)
    def create_learning_objective(
        module_id: str,
        payload: schemas.LearningObjectiveCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseModule, amo_id=amo_id, row_id=module_id, label="Course module")
        row = models.TrainingLearningObjective(amo_id=amo_id, module_id=module_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/course-revisions/{revision_id}/practical-tasks", status_code=201)
    def create_practical_task(
        revision_id: str,
        payload: schemas.PracticalTaskCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
        if payload.module_id:
            module = service._tenant_row(db, models.TrainingCourseModule, amo_id=amo_id, row_id=payload.module_id, label="Course module")
            if str(module.course_revision_id) != revision_id:
                raise HTTPException(status_code=409, detail="Practical task module does not belong to this course revision.")
        row = models.TrainingPracticalTask(amo_id=amo_id, course_revision_id=revision_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/course-revisions/{revision_id}/prerequisites", status_code=201)
    def create_prerequisite(
        revision_id: str,
        payload: schemas.PrerequisiteCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
        row = models.TrainingCoursePrerequisite(amo_id=amo_id, course_revision_id=revision_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/course-revisions/{revision_id}/references", status_code=201)
    def create_course_reference(
        revision_id: str,
        payload: schemas.CourseReferenceCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
        row = models.TrainingCourseReference(amo_id=amo_id, course_revision_id=revision_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/course-revisions/{revision_id}/materials", status_code=201)
    def create_material_revision(
        revision_id: str,
        payload: schemas.MaterialRevisionCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
        row = models.TrainingMaterialRevision(amo_id=amo_id, course_revision_id=revision_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.get("/operating/governance/course-revisions/{revision_id}/reconcile")
    def reconcile_course_revision(
        revision_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_VIEW)),
    ):
        return service.course_revision_reconciliation(db, amo_id=tenant_id_for(current_user), revision_id=revision_id)

    @router.post("/operating/governance/course-revisions/{revision_id}/activate", response_model=schemas.CourseRevisionRead)
    def activate_course_revision(
        revision_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=revision_id, label="Course revision")
        require_not_self_approval(actor_user_id=str(current_user.id), originator_user_id=row.created_by_user_id, action="approve")
        reconciliation = service.course_revision_reconciliation(db, amo_id=amo_id, revision_id=revision_id)
        blockers = list(reconciliation["blockers"])
        if not row.source_revision_id:
            blockers.append("Controlled source revision is missing.")
        if row.course_approval_id:
            approval = service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=row.course_approval_id, label="Course approval")
            blockers.extend(rules.approval_reasons(service._dict(approval), on_date=row.effective_from or date.today()))
        _, conflicts = service.list_effective_rules(db, amo_id=amo_id, on_date=row.effective_from or date.today(), context={"course_id": str(row.course_id)})
        if conflicts:
            blockers.append("Current controlled rules conflict for this course; resolve governance conflicts first.")
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "COURSE_REVISION_BLOCKED", "blockers": blockers})
        db.query(models.TrainingCourseRevision).filter(
            models.TrainingCourseRevision.amo_id == amo_id,
            models.TrainingCourseRevision.course_id == row.course_id,
            models.TrainingCourseRevision.id != row.id,
            models.TrainingCourseRevision.status == "ACTIVE",
        ).update({models.TrainingCourseRevision.status: "SUPERSEDED"}, synchronize_session=False)
        row.status = "ACTIVE"; row.approved_by_user_id = str(current_user.id)
        db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/facilities", response_model=list[schemas.FacilityRead])
    def list_facilities(
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_VIEW)),
    ):
        return db.query(models.TrainingFacility).filter(models.TrainingFacility.amo_id == tenant_id_for(current_user)).order_by(models.TrainingFacility.name).all()

    @router.post("/operating/governance/facilities", response_model=schemas.FacilityRead, status_code=201)
    def create_facility(
        payload: schemas.FacilityCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        if payload.approval_id:
            service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=payload.approval_id, label="Facility approval")
        row = models.TrainingFacility(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/facilities/{facility_id}/activate", response_model=schemas.FacilityRead)
    def activate_facility(
        facility_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = service._tenant_row(db, models.TrainingFacility, amo_id=amo_id, row_id=facility_id, label="Training facility")
        if row.approval_id:
            approval = service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=row.approval_id, label="Facility approval")
            blockers = rules.approval_reasons(service._dict(approval), on_date=date.today())
            if blockers:
                raise HTTPException(status_code=409, detail={"code": "FACILITY_APPROVAL_BLOCKED", "blockers": blockers})
        if not row.evidence_json:
            raise HTTPException(status_code=409, detail="Facility readiness evidence is required before activation.")
        row.status = "ACTIVE"; db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/providers", response_model=list[schemas.ProviderRead])
    def list_providers(
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_VIEW)),
    ):
        return db.query(models.TrainingProvider).filter(models.TrainingProvider.amo_id == tenant_id_for(current_user)).order_by(models.TrainingProvider.legal_name).all()

    @router.post("/operating/governance/providers", response_model=schemas.ProviderRead, status_code=201)
    def create_provider(
        payload: schemas.ProviderCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        if payload.approval_id:
            service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=payload.approval_id, label="Provider approval")
        row = models.TrainingProvider(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/providers/{provider_id}/activate", response_model=schemas.ProviderRead)
    def activate_provider(
        provider_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = service._tenant_row(db, models.TrainingProvider, amo_id=amo_id, row_id=provider_id, label="Training provider")
        if not row.approval_id or not row.evidence_json:
            raise HTTPException(status_code=409, detail="Provider approval and verification evidence are required before activation.")
        approval = service._tenant_row(db, models.TrainingApproval, amo_id=amo_id, row_id=row.approval_id, label="Provider approval")
        blockers = rules.approval_reasons(service._dict(approval), on_date=date.today())
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "PROVIDER_APPROVAL_BLOCKED", "blockers": blockers})
        row.status = "ACTIVE"; db.commit(); db.refresh(row)
        return row

    @router.post("/operating/governance/external-credit/check")
    def check_external_credit(
        payload: schemas.ExternalCreditCheck,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.PEOPLE_MANAGE)),
    ):
        return service.external_credit_check(db, amo_id=tenant_id_for(current_user), **payload.model_dump())

    @router.put("/operating/governance/events/{event_id}")
    def upsert_session_governance(
        event_id: str,
        payload: schemas.SessionGovernanceUpsert,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=event_id, label="Training session")
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=payload.course_revision_id, label="Course revision")
        if payload.facility_id:
            service._tenant_row(db, models.TrainingFacility, amo_id=amo_id, row_id=payload.facility_id, label="Training facility")
        if payload.provider_id:
            service._tenant_row(db, models.TrainingProvider, amo_id=amo_id, row_id=payload.provider_id, label="Training provider")
        for auth_id in payload.instructor_authorisation_ids + payload.examiner_authorisation_ids + payload.assessor_authorisation_ids:
            service._tenant_row(db, models.TrainingTechnicalAuthorisation, amo_id=amo_id, row_id=auth_id, label="Technical authorisation")
        row = db.query(models.TrainingSessionGovernance).filter(models.TrainingSessionGovernance.amo_id == amo_id, models.TrainingSessionGovernance.event_id == event_id).first()
        if row is None:
            row = models.TrainingSessionGovernance(amo_id=amo_id, event_id=event_id, **payload.model_dump())
            db.add(row)
        else:
            for key, value in payload.model_dump().items():
                setattr(row, key, value)
        db.flush()
        result = service.evaluate_session_readiness(db, amo_id=amo_id, event_id=event_id, persist=True)
        db.commit(); db.refresh(row)
        return {**service._dict(row), "readiness": result}

    @router.get("/operating/governance/events/{event_id}/readiness", response_model=schemas.SessionReadinessRead)
    def session_readiness(
        event_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_VIEW)),
    ):
        result = service.evaluate_session_readiness(db, amo_id=tenant_id_for(current_user), event_id=event_id, persist=True)
        db.commit()
        return result

    @router.post("/operating/governance/events/{event_id}/start")
    def start_session_under_governance(
        event_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        result = service.evaluate_session_readiness(db, amo_id=amo_id, event_id=event_id, persist=True)
        if result["status"] == "BLOCKED":
            db.commit()
            raise HTTPException(status_code=409, detail={"code": "SESSION_NOT_READY", "readiness": result})
        event = service._tenant_row(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=event_id, label="Training session")
        envelope = db.query(models.TrainingSessionGovernance).filter(models.TrainingSessionGovernance.amo_id == amo_id, models.TrainingSessionGovernance.event_id == event_id).one()
        event.status = legacy_models.TrainingEventStatus.IN_PROGRESS
        envelope.status = "IN_PROGRESS"
        db.commit()
        return {"event_id": event_id, "status": "IN_PROGRESS", "readiness": result}

    @router.put("/operating/governance/events/{event_id}/modules/{module_id}/attendance")
    def upsert_module_attendance(
        event_id: str,
        module_id: str,
        payload: schemas.ModuleAttendanceUpsert,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ATTENDANCE_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=event_id, label="Training session")
        service._tenant_row(db, models.TrainingCourseModule, amo_id=amo_id, row_id=module_id, label="Course module")
        participant = db.query(legacy_models.TrainingEventParticipant).filter(legacy_models.TrainingEventParticipant.amo_id == amo_id, legacy_models.TrainingEventParticipant.event_id == event_id, legacy_models.TrainingEventParticipant.user_id == payload.user_id).first()
        if not participant:
            raise HTTPException(status_code=409, detail="Only an enrolled learner can receive module attendance evidence.")
        row = db.query(models.TrainingModuleAttendance).filter(models.TrainingModuleAttendance.amo_id == amo_id, models.TrainingModuleAttendance.event_id == event_id, models.TrainingModuleAttendance.module_id == module_id, models.TrainingModuleAttendance.user_id == payload.user_id).first()
        if row is None:
            row = models.TrainingModuleAttendance(amo_id=amo_id, event_id=event_id, module_id=module_id, validated_by_user_id=str(current_user.id), validated_at=service._utcnow(), **payload.model_dump())
            db.add(row)
        else:
            previous = row.status
            for key, value in payload.model_dump().items():
                setattr(row, key, value)
            row.validated_by_user_id = str(current_user.id); row.validated_at = service._utcnow()
            if previous != row.status and not payload.correction_reason:
                raise HTTPException(status_code=422, detail="Changing module attendance status requires a correction reason.")
        db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/events/{event_id}/practical/{task_id}", status_code=201)
    def record_practical_assessment(
        event_id: str,
        task_id: str,
        payload: schemas.PracticalAssessmentCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_PERFORM)),
    ):
        amo_id = tenant_id_for(current_user)
        event = service._tenant_row(db, legacy_models.TrainingEvent, amo_id=amo_id, row_id=event_id, label="Training session")
        task = service._tenant_row(db, models.TrainingPracticalTask, amo_id=amo_id, row_id=task_id, label="Practical task")
        auth = service._tenant_row(db, models.TrainingTechnicalAuthorisation, amo_id=amo_id, row_id=payload.assessor_authorisation_id, label="Assessor authorisation")
        if str(auth.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="The assessor authorisation does not belong to the signed-in assessor.")
        readiness = service.technical_authorisation_readiness(db, amo_id=amo_id, user_id=str(current_user.id), privilege_type="ASSESSOR", on_date=event.starts_on, course_id=str(task.course_revision_id), require_practical=True)
        if not readiness["eligible"]:
            raise HTTPException(status_code=409, detail={"code": "ASSESSOR_NOT_ELIGIBLE", "reasons": readiness["reasons"]})
        row = models.TrainingPracticalAssessment(amo_id=amo_id, event_id=event_id, practical_task_id=task_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/questions", status_code=201)
    def create_question_item(
        payload: schemas.QuestionItemCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingCourseRevision, amo_id=amo_id, row_id=payload.course_revision_id, label="Course revision")
        row = models.TrainingQuestionBankItem(amo_id=amo_id, created_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/questions/{question_id}/revisions", status_code=201)
    def create_question_revision(
        question_id: str,
        payload: schemas.QuestionRevisionCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_CREATE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingQuestionBankItem, amo_id=amo_id, row_id=question_id, label="Question")
        row = models.TrainingQuestionRevision(amo_id=amo_id, question_id=question_id, author_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        data = service._dict(row)
        # This is an authoring endpoint, so answer_key_json is intentionally present.
        return data

    @router.post("/operating/governance/questions/{question_id}/revisions/{revision_id}/activate")
    def activate_question_revision(
        question_id: str,
        revision_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.ASSESSMENT_APPROVE)),
    ):
        amo_id = tenant_id_for(current_user)
        question = service._tenant_row(db, models.TrainingQuestionBankItem, amo_id=amo_id, row_id=question_id, label="Question")
        revision = service._tenant_row(db, models.TrainingQuestionRevision, amo_id=amo_id, row_id=revision_id, label="Question revision")
        if str(revision.question_id) != question_id:
            raise HTTPException(status_code=409, detail="Question revision does not belong to this question.")
        require_not_self_approval(actor_user_id=str(current_user.id), originator_user_id=revision.author_user_id, action="approve")
        blockers = rules.question_eligibility_reasons({**service._dict(question), "status": "ACTIVE"}, {**service._dict(revision), "status": "ACTIVE"}, on_date=revision.effective_from or date.today())
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "QUESTION_REVISION_BLOCKED", "blockers": blockers})
        db.query(models.TrainingQuestionRevision).filter(models.TrainingQuestionRevision.amo_id == amo_id, models.TrainingQuestionRevision.question_id == question_id, models.TrainingQuestionRevision.id != revision_id, models.TrainingQuestionRevision.status == "ACTIVE").update({models.TrainingQuestionRevision.status: "RETIRED"}, synchronize_session=False)
        revision.status = "ACTIVE"; revision.reviewer_user_id = str(current_user.id); revision.approved_by_user_id = str(current_user.id); question.status = "ACTIVE"
        db.commit(); db.refresh(revision)
        return {key: value for key, value in service._dict(revision).items() if key != "answer_key_json"}

    @router.get("/operating/governance/questions/revisions/{revision_id}/learner", response_model=schemas.QuestionLearnerRead)
    def learner_question(
        revision_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        revision = service._tenant_row(db, models.TrainingQuestionRevision, amo_id=tenant_id_for(current_user), row_id=revision_id, label="Question revision")
        question = service._tenant_row(db, models.TrainingQuestionBankItem, amo_id=tenant_id_for(current_user), row_id=revision.question_id, label="Question")
        blockers = rules.question_eligibility_reasons(service._dict(question), service._dict(revision), on_date=date.today())
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "QUESTION_NOT_AVAILABLE", "blockers": blockers})
        return service.learner_question_projection(revision)

    @router.post("/operating/governance/impact/preview", response_model=schemas.ImpactAssessmentRead, status_code=201)
    def preview_manual_impact(
        payload: schemas.ImpactPreviewCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.COURSE_MANAGE)),
    ):
        row = service.impact_preview(db, actor=current_user, **payload.model_dump())
        db.commit(); db.refresh(row)
        return row

    @router.get("/operating/governance/impact/{impact_id}/items")
    def impact_items(
        impact_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingImpactAssessment, amo_id=amo_id, row_id=impact_id, label="Impact assessment")
        rows = db.query(models.TrainingImpactItem).filter(models.TrainingImpactItem.amo_id == amo_id, models.TrainingImpactItem.impact_assessment_id == impact_id).order_by(models.TrainingImpactItem.blocking.desc(), models.TrainingImpactItem.entity_type).all()
        return [service._dict(row) for row in rows]

    @router.post("/operating/governance/completion/evaluate")
    def evaluate_learner_completion(
        payload: schemas.LearnerCompletionInput,
        current_user: account_models.User = Depends(require_training_capability(Cap.SESSION_CLOSE)),
    ):
        del current_user
        return rules.learner_completion_decision(**payload.model_dump())

    @router.post("/operating/governance/completion/batch-certificate")
    def evaluate_batch_certificates(
        payload: list[schemas.BatchCertificateCandidate],
        current_user: account_models.User = Depends(require_training_capability(Cap.CERTIFICATE_ISSUE)),
    ):
        del current_user
        return rules.batch_certificate_decisions([row.model_dump() for row in payload])

    @router.post("/operating/governance/authority-submissions", status_code=201)
    def create_authority_submission(
        payload: schemas.AuthoritySubmissionCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        service._tenant_row(db, models.TrainingAuthority, amo_id=amo_id, row_id=payload.authority_id, label="Training authority")
        row = models.TrainingAuthoritySubmission(amo_id=amo_id, **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/authority-submissions/{submission_id}/decision")
    def decide_authority_submission(
        submission_id: str,
        payload: schemas.AuthoritySubmissionDecision,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.SETTINGS_MANAGE)),
    ):
        amo_id = tenant_id_for(current_user)
        row = service._tenant_row(db, models.TrainingAuthoritySubmission, amo_id=amo_id, row_id=submission_id, label="Authority submission")
        if payload.status in {"APPROVED", "ACCEPTED"} and row.externally_received and not payload.independently_verified:
            raise HTTPException(status_code=409, detail="Externally received authority approval evidence must be independently verified before it becomes effective.")
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        if payload.independently_verified:
            row.verified_by_user_id = str(current_user.id)
        db.commit(); db.refresh(row)
        return service._dict(row)

    @router.post("/operating/governance/quality-links", status_code=201)
    def create_quality_link(
        payload: schemas.QualityLinkCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(require_training_capability(Cap.VIEW)),
    ):
        row = models.TrainingQualityLink(amo_id=tenant_id_for(current_user), created_by_user_id=str(current_user.id), **payload.model_dump())
        db.add(row); db.commit(); db.refresh(row)
        return service._dict(row)
