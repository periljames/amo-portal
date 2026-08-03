from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend/amodb/apps/reliability"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def patch_models() -> None:
    path = APP / "advanced_models.py"
    text = path.read_text(encoding="utf-8")
    old_threshold = '''    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    metric = relationship("ReliabilityMetricDefinition", back_populates="thresholds", lazy="joined")
'''
    new_threshold = '''    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    metric = relationship("ReliabilityMetricDefinition", back_populates="thresholds", lazy="joined")
'''
    text = replace_once(text, old_threshold, new_threshold, "threshold creator")
    old_authority = '''    response_json = Column(JSON_VALUE, nullable=False, default=dict)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
'''
    new_authority = '''    response_json = Column(JSON_VALUE, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
'''
    text = replace_once(text, old_authority, new_authority, "authority creator")
    path.write_text(text, encoding="utf-8")


def patch_schemas() -> None:
    path = APP / "advanced_schemas.py"
    text = path.read_text(encoding="utf-8")
    anchor = '''class EffectivenessReviewRead(ORMModel):
'''
    addition = '''class EffectivenessReviewApproval(BaseModel):
    rationale: str = Field(min_length=5, max_length=12000)


class EffectivenessReviewRead(ORMModel):
'''
    text = replace_once(text, anchor, addition, "effectiveness approval schema")
    path.write_text(text, encoding="utf-8")


def patch_services() -> None:
    path = APP / "advanced_services.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '''    actor_user_id: str,
    approve: bool,
) -> domain.ReliabilityEffectivenessReview:''',
        '''    actor_user_id: str,
) -> domain.ReliabilityEffectivenessReview:''',
        1,
    )
    text = text.replace(
        '''        reviewer_user_id=actor_user_id,
        approved_by_user_id=actor_user_id if approve else None,
        approved_at=utcnow() if approve else None,
''',
        '''        reviewer_user_id=actor_user_id,
        approved_by_user_id=None,
        approved_at=None,
''',
        1,
    )
    text = text.replace(
        '''        payload={"review_id": review.id, "outcome": review.outcome, "approved": bool(review.approved_at)},
''',
        '''        payload={"review_id": review.id, "outcome": review.outcome, "approved": False},
''',
        1,
    )
    list_anchor = '''def list_effectiveness_reviews(db: Session, *, amo_id: str, case_id: int) -> Sequence[domain.ReliabilityEffectivenessReview]:
'''
    approval_function = '''def approve_effectiveness_review(
    db: Session,
    *,
    amo_id: str,
    case_id: int,
    review_id: str,
    rationale: str,
    actor_user_id: str,
) -> domain.ReliabilityEffectivenessReview:
    lifecycle = ensure_fracas_lifecycle(db, amo_id=amo_id, case_id=case_id, actor_user_id=actor_user_id)
    review = (
        db.query(domain.ReliabilityEffectivenessReview)
        .filter(
            domain.ReliabilityEffectivenessReview.amo_id == amo_id,
            domain.ReliabilityEffectivenessReview.lifecycle_id == lifecycle.id,
            domain.ReliabilityEffectivenessReview.id == review_id,
        )
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="Effectiveness review not found.")
    if review.approved_at:
        raise HTTPException(status_code=409, detail="Effectiveness review is already approved.")
    if str(review.reviewer_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The effectiveness reviewer cannot approve their own review.")
    review.approved_by_user_id = actor_user_id
    review.approved_at = utcnow()
    review.notes = f"{review.notes or ''}\nApproval rationale: {rationale}".strip()
    append_audit(
        db,
        amo_id=amo_id,
        entity_type="FRACAS_CASE",
        entity_id=str(case_id),
        action="EFFECTIVENESS_REVIEW_APPROVED",
        payload={"review_id": review.id, "outcome": review.outcome, "rationale": rationale},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(review)
    return review


def list_effectiveness_reviews(db: Session, *, amo_id: str, case_id: int) -> Sequence[domain.ReliabilityEffectivenessReview]:
'''
    text = replace_once(text, list_anchor, approval_function, "effectiveness approval function")

    programme_guard = '''    if payload.to_status == "APPROVED":
        metric_count = db.query(func.count(domain.ReliabilityMetricDefinition.id)).filter(
'''
    programme_guard_new = '''    if payload.to_status == "APPROVED":
        if str(version.created_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The programme-version author cannot approve their own version.")
        metric_count = db.query(func.count(domain.ReliabilityMetricDefinition.id)).filter(
'''
    text = replace_once(text, programme_guard, programme_guard_new, "programme SoD guard")

    threshold_create = '''        rationale=payload.rationale,
        effective_from=payload.effective_from,
    )
'''
    threshold_create_new = '''        rationale=payload.rationale,
        effective_from=payload.effective_from,
        created_by_user_id=actor_user_id,
    )
'''
    text = replace_once(text, threshold_create, threshold_create_new, "threshold creator assignment")
    threshold_guard = '''    if payload.to_status not in allowed.get(threshold.status, set()):
        raise HTTPException(status_code=409, detail=f"Threshold transition {threshold.status} -> {payload.to_status} is not permitted.")
    old = threshold.status
'''
    threshold_guard_new = '''    if payload.to_status not in allowed.get(threshold.status, set()):
        raise HTTPException(status_code=409, detail=f"Threshold transition {threshold.status} -> {payload.to_status} is not permitted.")
    if payload.to_status in {"APPROVED", "EFFECTIVE"} and str(threshold.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The threshold author cannot approve or activate their own threshold.")
    old = threshold.status
'''
    text = replace_once(text, threshold_guard, threshold_guard_new, "threshold SoD guard")

    meeting_guard = '''    if payload.to_status == "APPROVED":
        meeting.minutes = payload.minutes or meeting.minutes
'''
    meeting_guard_new = '''    if payload.to_status == "APPROVED":
        if str(meeting.chaired_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The meeting chair cannot independently approve their own minutes.")
        meeting.minutes = payload.minutes or meeting.minutes
'''
    text = replace_once(text, meeting_guard, meeting_guard_new, "meeting SoD guard")

    change_guard = '''    if payload.to_status in {"APPROVED", "IMPLEMENTED"} and not proposal.impact_assessment_json:
        raise HTTPException(status_code=409, detail="A controlled impact assessment is required.")
'''
    change_guard_new = '''    if payload.to_status == "APPROVED" and str(proposal.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The change author cannot approve their own proposal.")
    if payload.to_status in {"APPROVED", "IMPLEMENTED"} and not proposal.impact_assessment_json:
        raise HTTPException(status_code=409, detail="A controlled impact assessment is required.")
'''
    text = replace_once(text, change_guard, change_guard_new, "change SoD guard")

    authority_create = '''    submission = domain.ReliabilityAuthoritySubmission(amo_id=amo_id, **payload.model_dump())
'''
    authority_create_new = '''    submission = domain.ReliabilityAuthoritySubmission(
        amo_id=amo_id,
        created_by_user_id=actor_user_id,
        **payload.model_dump(),
    )
'''
    text = replace_once(text, authority_create, authority_create_new, "authority creator assignment")
    authority_guard = '''    if payload.to_status == "SUBMITTED":
        if submission.status != "READY":
            raise HTTPException(status_code=409, detail="Only a READY package can be submitted.")
        submission.submitted_by_user_id = actor_user_id
'''
    authority_guard_new = '''    if payload.to_status == "SUBMITTED":
        if submission.status != "READY":
            raise HTTPException(status_code=409, detail="Only a READY package can be submitted.")
        if str(submission.created_by_user_id) == str(actor_user_id):
            raise HTTPException(status_code=409, detail="The authority-package preparer cannot submit their own package.")
        submission.submitted_by_user_id = actor_user_id
'''
    text = replace_once(text, authority_guard, authority_guard_new, "authority SoD guard")

    ai_guard = '''    if review.status not in {"DRAFT", "REVIEWED"}:
        raise HTTPException(status_code=409, detail="This AI review already has a final human decision.")
    review.status = payload.decision
'''
    ai_guard_new = '''    if review.status not in {"DRAFT", "REVIEWED"}:
        raise HTTPException(status_code=409, detail="This AI review already has a final human decision.")
    if str(review.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The AI-review requester cannot provide the final human disposition.")
    review.status = payload.decision
'''
    text = replace_once(text, ai_guard, ai_guard_new, "AI SoD guard")
    path.write_text(text, encoding="utf-8")


def patch_router() -> None:
    path = APP / "advanced_router.py"
    text = path.read_text(encoding="utf-8")
    old = '''@router.post("/fracas/cases/{case_id:int}/effectiveness", response_model=schemas.EffectivenessReviewRead, status_code=201)
def add_effectiveness_review(
    case_id: int,
    payload: schemas.EffectivenessReviewCreate,
    approve: bool = False,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.fracas.verify")
    return services.create_effectiveness_review(
        db,
        amo_id=amo_id,
        case_id=case_id,
        payload=payload,
        actor_user_id=str(current_user.id),
        approve=approve,
    )
'''
    new = '''@router.post("/fracas/cases/{case_id:int}/effectiveness", response_model=schemas.EffectivenessReviewRead, status_code=201)
def add_effectiveness_review(
    case_id: int,
    payload: schemas.EffectivenessReviewCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.fracas.verify")
    return services.create_effectiveness_review(
        db,
        amo_id=amo_id,
        case_id=case_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/fracas/cases/{case_id:int}/effectiveness/{review_id}/approve", response_model=schemas.EffectivenessReviewRead)
def approve_effectiveness_review(
    case_id: int,
    review_id: str,
    payload: schemas.EffectivenessReviewApproval,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.fracas.verify")
    return services.approve_effectiveness_review(
        db,
        amo_id=amo_id,
        case_id=case_id,
        review_id=review_id,
        rationale=payload.rationale,
        actor_user_id=str(current_user.id),
    )
'''
    text = replace_once(text, old, new, "effectiveness routes")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_models()
    patch_schemas()
    patch_services()
    patch_router()
    print("Reliability segregation-of-duties controls applied.")


if __name__ == "__main__":
    main()
