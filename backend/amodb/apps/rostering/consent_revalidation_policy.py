from __future__ import annotations

from ..accounts import models as account_models
from . import common, consent_service, models, validation

_INSTALLED = False


def _planner_email(db, *, amo_id: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    row = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
    ).first()
    return getattr(row, "email", None) if row else None


def _revalidate_and_notify_if_ready(
    db,
    *,
    amo_id: str,
    version_id: str,
    actor_user_id: str | None,
) -> None:
    """Recalculate authoritative compliance after each workflow decision.

    Consent and supervisor approval are prerequisites only. They never mutate a
    statutory finding into PASS. A roster becomes ready only when the canonical
    validator has just run against the current version and every consent task is
    independently complete.
    """

    version = common.get_version(db, amo_id=amo_id, version_id=version_id, lock=True)
    if version is None:
        return
    result = validation.run_validation(
        db,
        version=version,
        actor_user_id=actor_user_id,
    )
    if result.blocker_count:
        return
    try:
        consent_service.assert_version_ready(
            db,
            version=version,
            actor_user_id=actor_user_id,
        )
    except consent_service.RosterWorkflowError:
        return

    # Readiness notification is relevant while the roster is still awaiting
    # organizational approval. Correlation by validation fingerprint keeps the
    # same authoritative state idempotent in the existing notification layer.
    if version.status != models.RosterVersionStatus.DRAFT:
        return
    fingerprint = result.validation_fingerprint or version.validation_fingerprint or "unfingerprinted"
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterVersion",
        entity_id=version.id,
        action="roster_ready_for_approval",
        after={
            "validation_fingerprint": fingerprint,
            "blocker_count": result.blocker_count,
            "warning_count": result.warning_count,
        },
        critical=True,
    )
    common.notify_email(
        db,
        amo_id=version.amo_id,
        recipient=_planner_email(
            db,
            amo_id=version.amo_id,
            user_id=version.created_by_user_id,
        ),
        template_key="roster_ready_for_approval",
        subject="Roster ready for approval",
        context={
            "version_id": version.id,
            "period_id": version.period_id,
            "validation_fingerprint": fingerprint,
            "warning_count": result.warning_count,
        },
        correlation_id=f"roster-ready-for-approval:{version.id}:{fingerprint}",
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_respond = consent_service.respond
    original_supervisor_decide = consent_service.supervisor_decide

    def respond(db, *, request, actor, accept, comment=None):
        row = original_respond(
            db,
            request=request,
            actor=actor,
            accept=accept,
            comment=comment,
        )
        _revalidate_and_notify_if_ready(
            db,
            amo_id=row.amo_id,
            version_id=row.version_id,
            actor_user_id=actor.id,
        )
        return row

    def supervisor_decide(db, *, request, actor, approve, comment=None):
        row = original_supervisor_decide(
            db,
            request=request,
            actor=actor,
            approve=approve,
            comment=comment,
        )
        _revalidate_and_notify_if_ready(
            db,
            amo_id=row.amo_id,
            version_id=row.version_id,
            actor_user_id=actor.id,
        )
        return row

    consent_service.respond = respond
    consent_service.supervisor_decide = supervisor_decide
    _INSTALLED = True


__all__ = ["install"]
