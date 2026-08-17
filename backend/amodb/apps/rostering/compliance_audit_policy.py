from __future__ import annotations

from ..accounts import models as account_models
from . import common, consent_service, models, validation

_INSTALLED = False


def _key(row: models.RosterValidationFinding) -> tuple[str, str | None, str | None]:
    return row.code, row.user_id, row.assignment_id


def _planner_email(db, *, version: models.RosterVersion) -> str | None:
    if not version.created_by_user_id:
        return None
    row = db.query(account_models.User).filter(
        account_models.User.amo_id == version.amo_id,
        account_models.User.id == version.created_by_user_id,
        account_models.User.is_active.is_(True),
    ).first()
    return getattr(row, "email", None) if row else None


def install() -> None:
    """Trace compliance evaluation and blocker resolution through audit/notifications."""

    global _INSTALLED
    if _INSTALLED:
        return

    original = validation.run_validation

    def run_validation(db, *, version, actor_user_id=None):
        previous_rows = db.query(models.RosterValidationFinding).filter(
            models.RosterValidationFinding.amo_id == version.amo_id,
            models.RosterValidationFinding.version_id == version.id,
            models.RosterValidationFinding.severity == models.RosterValidationSeverity.BLOCKER,
            models.RosterValidationFinding.resolved.is_(False),
        ).all()
        previous = {_key(row) for row in previous_rows}

        result = original(db, version=version, actor_user_id=actor_user_id)
        current_rows = [
            row for row in (version.validation_findings or [])
            if row.severity == models.RosterValidationSeverity.BLOCKER and not row.resolved
        ]
        current = {_key(row) for row in current_rows}

        common.audit(
            db,
            amo_id=version.amo_id,
            actor_user_id=actor_user_id,
            entity_type="RosterVersion",
            entity_id=version.id,
            action="roster_compliance_evaluated",
            after={
                "validation_fingerprint": result.validation_fingerprint,
                "blocker_count": result.blocker_count,
                "warning_count": result.warning_count,
                "info_count": result.info_count,
            },
            critical=bool(result.blocker_count),
        )

        generated = current - previous
        resolved = previous - current
        for code, personnel_id, assignment_id in sorted(generated):
            common.audit(
                db,
                amo_id=version.amo_id,
                actor_user_id=actor_user_id,
                entity_type="RosterVersion",
                entity_id=version.id,
                action="roster_hard_blocker_generated",
                metadata={
                    "code": code,
                    "personnel_id": personnel_id,
                    "assignment_id": assignment_id,
                },
                critical=True,
            )
        for code, personnel_id, assignment_id in sorted(resolved):
            common.audit(
                db,
                amo_id=version.amo_id,
                actor_user_id=actor_user_id,
                entity_type="RosterVersion",
                entity_id=version.id,
                action="roster_hard_blocker_resolved",
                metadata={
                    "code": code,
                    "personnel_id": personnel_id,
                    "assignment_id": assignment_id,
                },
                critical=True,
            )

        recipient = _planner_email(db, version=version)
        if generated and recipient:
            common.notify_email(
                db,
                amo_id=version.amo_id,
                recipient=recipient,
                template_key="roster_compliance_blocked",
                subject="Roster compliance action required",
                context={
                    "version_id": version.id,
                    "blockers": [
                        {"code": code, "personnel_id": person, "assignment_id": assignment}
                        for code, person, assignment in sorted(generated)
                    ],
                },
                correlation_id=f"roster-compliance-blocked:{version.id}:{result.validation_fingerprint}",
            )
        if not current and previous and recipient:
            try:
                consent_service.assert_version_ready(
                    db,
                    version=version,
                    actor_user_id=actor_user_id,
                )
            except consent_service.RosterWorkflowError:
                pass
            else:
                common.notify_email(
                    db,
                    amo_id=version.amo_id,
                    recipient=recipient,
                    template_key="roster_ready_for_approval",
                    subject="Roster is ready for approval",
                    context={"version_id": version.id},
                    correlation_id=f"roster-ready-for-approval:{version.id}:{result.validation_fingerprint}",
                )
        return result

    validation.run_validation = run_validation
    _INSTALLED = True


__all__ = ["install"]
