from __future__ import annotations

from typing import Any

from . import consent_service, models

_INSTALLED = False


def _finding_payload(row: models.RosterValidationFinding) -> dict[str, Any]:
    details = dict(row.details_json or {})
    return {
        "finding_id": row.id,
        "code": row.code,
        "message": row.message,
        "severity": str(getattr(row.severity, "value", row.severity)),
        "assignment_id": row.assignment_id,
        "personnel_id": row.user_id,
        "rule_id": row.rule_id,
        "window_start": details.get("window_start"),
        "window_end": details.get("window_end"),
        "longest_rest_minutes": details.get("longest_rest_minutes"),
        "required_rest_minutes": details.get("required_rest_minutes"),
        "remediation_actions": list(details.get("remediation_actions") or []),
        "details": details,
    }


def _raise_compliance_error(version: models.RosterVersion, exc: Exception) -> None:
    message = str(exc)
    if "unresolved blocker" not in message.lower():
        raise exc
    blockers = [
        row
        for row in (version.validation_findings or [])
        if row.severity == models.RosterValidationSeverity.BLOCKER and not row.resolved
    ]
    payload = [_finding_payload(row) for row in blockers]
    protected = next((row for row in blockers if row.code == "ROSTER_PROTECTED_REST_VIOLATION"), None)
    code = protected.code if protected is not None else "ROSTER_COMPLIANCE_BLOCKED"
    remediation = sorted({
        action
        for item in payload
        for action in item.get("remediation_actions", [])
    })
    raise consent_service.RosterWorkflowError(
        code,
        protected.message if protected is not None else message,
        {
            "version_id": version.id,
            "workflow_severity": "HARD_BLOCK",
            "blockers": payload,
            "remediation_actions": remediation,
            "personnel_acknowledgement_can_cure": False,
            "managerial_override_allowed": False,
        },
    ) from exc


def install_service_policy(service_module) -> None:
    """Attach domain-specific blocker metadata to lifecycle failures."""

    global _INSTALLED
    if _INSTALLED:
        return

    for name in ("submit_version", "approve_version", "publish_version"):
        original = getattr(service_module, name)

        def governed(db, *, version, actor_user_id: str, payload, _original=original):
            try:
                return _original(
                    db,
                    version=version,
                    actor_user_id=actor_user_id,
                    payload=payload,
                )
            except consent_service.RosterWorkflowError:
                raise
            except (ValueError, RuntimeError) as exc:
                _raise_compliance_error(version, exc)

        setattr(service_module, name, governed)

    _INSTALLED = True


__all__ = ["install_service_policy"]
