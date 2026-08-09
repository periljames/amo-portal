from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import formal_reporting as core
from .formal_reporting_models import (
    FormalReportStatus,
    ReliabilityFormalApproval,
    ReliabilityFormalReport,
)


def _supersede_prior(
    db: Session,
    replacement: ReliabilityFormalReport,
    user: account_models.User,
    *,
    comment: str | None,
    now: datetime,
) -> ReliabilityFormalReport | None:
    prior_id = replacement.supersedes_report_id
    if not prior_id:
        return None
    if prior_id == replacement.id:
        raise HTTPException(status_code=409, detail="A formal report revision cannot supersede itself.")

    prior = core._report(db, replacement.amo_id, prior_id)
    if prior.status != FormalReportStatus.PUBLISHED.value or prior.published_at is None:
        raise HTTPException(
            status_code=409,
            detail="A replacement revision can only supersede the currently published prior revision.",
        )
    if prior.report_number != replacement.report_number:
        raise HTTPException(
            status_code=409,
            detail="A replacement revision must retain the controlled report number of the revision it supersedes.",
        )
    if prior.revision >= replacement.revision:
        raise HTTPException(
            status_code=409,
            detail="A replacement revision must have a greater revision number than the published revision it supersedes.",
        )

    competing = db.query(ReliabilityFormalReport.id).filter(
        ReliabilityFormalReport.amo_id == replacement.amo_id,
        ReliabilityFormalReport.report_number == replacement.report_number,
        ReliabilityFormalReport.status == FormalReportStatus.PUBLISHED.value,
        ReliabilityFormalReport.id.notin_([prior.id, replacement.id]),
    ).first()
    if competing:
        raise HTTPException(
            status_code=409,
            detail="Another published revision exists for this controlled report number. Resolve the publication chain first.",
        )

    previous = prior.status
    prior.status = FormalReportStatus.SUPERSEDED.value
    prior.superseded_at = now
    prior.superseded_by_user_id = user.id
    db.add(ReliabilityFormalApproval(
        amo_id=prior.amo_id,
        report_id=prior.id,
        stage=previous,
        decision=FormalReportStatus.SUPERSEDED.value,
        actor_user_id=user.id,
        role_snapshot=core._role(user),
        comment=comment or f"Superseded by {replacement.report_number} Rev {replacement.revision} publication.",
        report_revision=prior.revision,
        report_hash=prior.pdf_sha256 or prior.html_sha256,
    ))
    core._append_lifecycle(
        db,
        prior,
        from_status=previous,
        to_status=FormalReportStatus.SUPERSEDED.value,
        action="SUPERSEDED_BY_PUBLICATION",
        actor=user,
        rationale=comment,
        payload={
            "replacement_report_id": replacement.id,
            "replacement_report_number": replacement.report_number,
            "replacement_revision": replacement.revision,
            "replacement_hash": replacement.pdf_sha256 or replacement.html_sha256,
        },
    )
    return prior


def transition_report(
    db: Session,
    report: ReliabilityFormalReport,
    user: account_models.User,
    payload: core.TransitionRequest,
) -> ReliabilityFormalReport:
    """Formal lifecycle transition with atomic replacement-publication semantics.

    This intentionally mirrors the core lifecycle gate while adding the missing
    controlled-publication invariant: when an approved revision declares
    ``supersedes_report_id``, the replacement becomes PUBLISHED and the prior
    published revision becomes SUPERSEDED in the same database transaction.
    """
    core._require_human(user)
    target = payload.to_status.value
    allowed = core.ALLOWED_TRANSITIONS.get(report.status, set())
    if target not in allowed:
        raise HTTPException(status_code=409, detail=f"Transition {report.status} -> {target} is not allowed.")

    profile = core._profile(db, report.amo_id, report.profile_id)
    core._require_role(
        user,
        core._roles_for_transition(profile, target),
        "Your role cannot perform this formal Reliability transition.",
    )

    if (
        bool((profile.approval_workflow or {}).get("separation_of_duties", True))
        and target in {FormalReportStatus.APPROVED.value, FormalReportStatus.PUBLISHED.value}
        and report.created_by_user_id == user.id
        and not bool(getattr(user, "is_superuser", False))
    ):
        raise HTTPException(
            status_code=409,
            detail="Separation of duties prevents the preparer approving/publishing the same report revision.",
        )

    if target in {
        FormalReportStatus.APPROVAL_PENDING.value,
        FormalReportStatus.APPROVED.value,
        FormalReportStatus.PUBLISHED.value,
    }:
        result = core.completeness_result(db, report, persist=True)
        if not result["passed"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Formal Reliability report completeness gate failed.",
                    "blocking_failures": result["blocking_failures"],
                },
            )

    previous = report.status
    now = datetime.now(core.UTC)
    report.status = target
    if target == FormalReportStatus.PUBLISHED.value:
        report.published_at = now
        report.published_by_user_id = user.id
        _supersede_prior(db, report, user, comment=payload.comment, now=now)
    elif target == FormalReportStatus.SUPERSEDED.value:
        report.superseded_at = now
        report.superseded_by_user_id = user.id
    elif target == FormalReportStatus.WITHDRAWN.value:
        report.withdrawn_at = now
        report.withdrawn_by_user_id = user.id

    db.add(ReliabilityFormalApproval(
        amo_id=report.amo_id,
        report_id=report.id,
        stage=previous,
        decision=target,
        actor_user_id=user.id,
        role_snapshot=core._role(user),
        comment=payload.comment,
        report_revision=report.revision,
        report_hash=report.pdf_sha256 or report.html_sha256,
    ))
    core._append_lifecycle(
        db,
        report,
        from_status=previous,
        to_status=target,
        action="TRANSITION",
        actor=user,
        rationale=payload.comment,
        payload={
            "report_hash": report.pdf_sha256 or report.html_sha256,
            "supersedes_report_id": report.supersedes_report_id,
        },
    )
    db.commit()
    db.refresh(report)
    return report


def apply() -> None:
    if getattr(core, "_formal_supersession_patch_applied", False):
        return
    core._transition_report = transition_report
    core._formal_supersession_patch_applied = True
