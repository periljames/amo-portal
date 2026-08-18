from __future__ import annotations

from . import common, consent_service, extended_duty_service, models, validation

_INSTALLED = False


def install() -> None:
    """Require the active daily-duty rule to explicitly permit the same extension."""

    global _INSTALLED
    if _INSTALLED:
        return
    original = extended_duty_service.propose_extension

    def propose_extension(db, **kwargs):
        amo_id = kwargs["amo_id"]
        assignment_id = kwargs["assignment_id"]
        actor_user_id = kwargs["actor_user_id"]
        assignment = common.get_assignment(
            db,
            amo_id=amo_id,
            assignment_id=assignment_id,
            lock=True,
        )
        if assignment is None:
            raise consent_service.RosterWorkflowError(
                "ROSTER_ASSIGNMENT_NOT_FOUND",
                "Roster assignment was not found in this tenant.",
                {"assignment_id": assignment_id},
            )
        rules = validation.active_rules(
            db,
            amo_id=amo_id,
            on_date=assignment.version.period.starts_on,
        )
        day_rule = validation.find_rule(
            rules,
            models.RosterRuleType.MAX_DUTY_HOURS_DAY,
            assignment,
        )
        daily_maximum = None
        if day_rule is not None:
            parameters = dict(day_rule.parameters_json or {})
            if parameters.get("allow_unscheduled_unserviceability_extension") is not True:
                raise consent_service.RosterWorkflowError(
                    "ROSTER_DUTY_EXTENSION_NOT_PERMITTED",
                    "The active daily-duty rule does not permit an unscheduled-aircraft extension.",
                    {"assignment_id": assignment_id, "rule_code": day_rule.code},
                )
            daily_maximum = int(parameters.get("extended_maximum_minutes") or 0)
            if daily_maximum <= 0:
                raise consent_service.RosterWorkflowError(
                    "ROSTER_DUTY_EXTENSION_NOT_PERMITTED",
                    "The active daily-duty rule must define an extended maximum before this extension can be used.",
                    {"assignment_id": assignment_id, "rule_code": day_rule.code},
                )

        row = original(db, **kwargs)
        if daily_maximum is not None:
            fatigue = dict(row.fatigue_risk_json or {})
            fatigue["extended_daily_maximum_minutes"] = daily_maximum
            fatigue["daily_rule_code"] = day_rule.code if day_rule else None
            row.fatigue_risk_json = fatigue
            db.add(row)
            db.flush()
            result = validation.run_validation(
                db,
                version=assignment.version,
                actor_user_id=actor_user_id,
            )
            snapshot = {
                "blocker_count": result.blocker_count,
                "warning_count": result.warning_count,
                "validation_fingerprint": result.validation_fingerprint,
                "finding_codes": [item.code for item in result.findings if not item.resolved],
            }
            row.compliance_snapshot_json = snapshot
            if row.consent is not None:
                row.consent.statutory_compliance_json = snapshot
                db.add(row.consent)
            db.add(row)
        return row

    extended_duty_service.propose_extension = propose_extension
    _INSTALLED = True


__all__ = ["install"]
