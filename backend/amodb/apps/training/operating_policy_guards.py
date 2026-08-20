from __future__ import annotations

from typing import Callable

from fastapi import HTTPException
from sqlalchemy import func

from . import operating_models


def _amo_id(actor) -> str:
    value = getattr(actor, "effective_amo_id", None) or getattr(actor, "amo_id", None)
    if not value:
        raise HTTPException(status_code=403, detail="Select an AMO tenant before using Training.")
    return str(value)


def bridge_settings_creation(base: Callable):
    def get_or_create_settings(db, *, amo_id: str):
        existed = db.query(operating_models.TrainingOperatingSettings.id).filter(
            operating_models.TrainingOperatingSettings.amo_id == amo_id
        ).first()
        row = base(db, amo_id=amo_id)
        if existed is None and int(row.configuration_revision_no or 0) == 0:
            row.default_committee_positions = []
        return row
    return get_or_create_settings


def guard_submit_assessment(base: Callable):
    def submit_assessment(db, *, actor, assessment_id: str, payload):
        amo_id = _amo_id(actor)
        instance = db.query(operating_models.TrainingAssessmentInstance).filter(
            operating_models.TrainingAssessmentInstance.id == assessment_id,
            operating_models.TrainingAssessmentInstance.amo_id == amo_id,
        ).first()
        if instance is None:
            raise HTTPException(status_code=404, detail="Assessment was not found in this tenant.")
        template = db.query(operating_models.TrainingAssessmentTemplate).filter(
            operating_models.TrainingAssessmentTemplate.id == instance.template_id,
            operating_models.TrainingAssessmentTemplate.amo_id == amo_id,
        ).first()
        if template is None:
            raise HTTPException(status_code=409, detail="Assessment template is unavailable.")
        if str(template.outcome_scheme or "").upper() == "NUMERIC" and template.pass_threshold is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_THRESHOLD_NOT_CONFIGURED",
                    "message": "This numeric assessment has no tenant-controlled pass threshold. Configure the threshold before recording an outcome.",
                },
            )
        return base(db, actor=actor, assessment_id=assessment_id, payload=payload)
    return submit_assessment


def guard_create_authorization_case(base: Callable):
    def create_authorization_case(db, *, actor, payload):
        positions = list(payload.required_committee_positions or [])
        if not positions:
            amo_id = _amo_id(actor)
            settings = db.query(operating_models.TrainingOperatingSettings).filter(
                operating_models.TrainingOperatingSettings.amo_id == amo_id
            ).first()
            positions = list(settings.default_committee_positions or []) if settings else []
            if not positions:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTHORIZATION_COMMITTEE_POLICY_MISSING",
                        "message": "Configure the tenant authorization committee or select the required committee positions for this case.",
                    },
                )
            payload = payload.model_copy(update={"required_committee_positions": positions})
        return base(db, actor=actor, payload=payload)
    return create_authorization_case


def guard_create_controlled_form(base: Callable):
    def create_controlled_form(db, *, actor, payload):
        amo_id = _amo_id(actor)
        code = str(payload.code or "").strip().upper()
        existing = db.query(operating_models.TrainingControlledFormTemplate).filter(
            operating_models.TrainingControlledFormTemplate.amo_id == amo_id,
            func.upper(operating_models.TrainingControlledFormTemplate.code) == code,
        ).order_by(operating_models.TrainingControlledFormTemplate.revision_no.desc()).first()
        if existing is not None and str(existing.workflow or "").upper() != str(payload.workflow or "").upper():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTROLLED_FORM_IDENTITY_CONFLICT",
                    "message": "That tenant-controlled form number/code already belongs to another Training workflow.",
                    "form_number": code,
                    "existing_workflow": existing.workflow,
                    "requested_workflow": payload.workflow,
                },
            )
        return base(db, actor=actor, payload=payload)
    return create_controlled_form


def guard_transition_controlled_form(base: Callable):
    def transition_controlled_form(db, *, actor, form_id: str, target: str):
        amo_id = _amo_id(actor)
        row = db.query(operating_models.TrainingControlledFormTemplate).filter(
            operating_models.TrainingControlledFormTemplate.id == form_id,
            operating_models.TrainingControlledFormTemplate.amo_id == amo_id,
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Controlled form was not found in this tenant.")
        if str(target or "").upper() == "ACTIVE" and str(row.created_by_user_id or "") == str(actor.id):
            raise HTTPException(
                status_code=409,
                detail={"code": "SELF_APPROVAL_BLOCKED", "message": "The author of a controlled Training form revision cannot activate the same revision."},
            )
        return base(db, actor=actor, form_id=form_id, target=target)
    return transition_controlled_form


__all__ = [
    "bridge_settings_creation",
    "guard_create_authorization_case",
    "guard_create_controlled_form",
    "guard_submit_assessment",
    "guard_transition_controlled_form",
]
