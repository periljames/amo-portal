from __future__ import annotations

from datetime import datetime

from ..accounts import models as account_models
from . import compliance_policy, exemption_service, models, validation

_INSTALLED = False


def _assignment_ids(spec: validation.FindingSpec) -> list[str]:
    ids: set[str] = set()
    if spec.assignment_id:
        ids.add(str(spec.assignment_id))
    for interval in (spec.details or {}).get("duty_intervals", []):
        ids.update(str(item) for item in interval.get("assignment_ids", []) if item)
    return sorted(ids)


def _rule_code(spec: validation.FindingSpec) -> str:
    return str((spec.details or {}).get("rule_code") or spec.code).upper()


def _finding_date(spec: validation.FindingSpec, version) -> object:
    raw = (spec.details or {}).get("window_start")
    if raw:
        try:
            return datetime.fromisoformat(str(raw)).date()
        except ValueError:
            pass
    return version.period.starts_on


def install_validation_policy() -> None:
    """Replace an exempted statutory blocker with an auditable exemption result.

    The underlying violation remains in details. Internal approvals never reach
    this path; only a verified, in-date Authority record that explicitly covers
    the statutory rule can change the publication result.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    original_build_findings = validation.build_findings

    def governed_build_findings(db, *, version, rules):
        specs = original_build_findings(db, version=version, rules=rules)
        governed: list[validation.FindingSpec] = []
        user_cache: dict[str, account_models.User | None] = {}
        for spec in specs:
            rule_code = _rule_code(spec)
            statutory = (
                spec.severity == models.RosterValidationSeverity.BLOCKER
                and compliance_policy.statutory_rule_is_non_overridable(rule_code)
            )
            if not statutory:
                governed.append(spec)
                continue
            if spec.user_id not in user_cache:
                user_cache[spec.user_id or ""] = (
                    db.query(account_models.User)
                    .filter(
                        account_models.User.amo_id == version.amo_id,
                        account_models.User.id == spec.user_id,
                    )
                    .first()
                    if spec.user_id
                    else None
                )
            exemption = exemption_service.applicable_exemption(
                db,
                amo_id=version.amo_id,
                user=user_cache.get(spec.user_id or ""),
                rule_code=rule_code,
                on_date=_finding_date(spec, version),
                assignment_ids=_assignment_ids(spec),
            )
            if exemption is None:
                governed.append(spec)
                continue
            governed.append(validation.FindingSpec(
                source=models.RosterValidationSource.RULE,
                severity=models.RosterValidationSeverity.INFO,
                code="ROSTER_COMPLIANT_UNDER_VERIFIED_REGULATORY_EXEMPTION",
                message=(
                    "Compliant under verified regulatory exemption "
                    f"{exemption.authority} {exemption.exemption_reference}."
                ),
                assignment_id=spec.assignment_id,
                user_id=spec.user_id,
                rule_id=spec.rule_id,
                details={
                    "underlying_violation": {
                        "code": spec.code,
                        "message": spec.message,
                        "severity": str(getattr(spec.severity, "value", spec.severity)),
                        "details": spec.details,
                    },
                    "exemption": {
                        "id": exemption.id,
                        "authority": exemption.authority,
                        "reference": exemption.exemption_reference,
                        "regulation_provision": exemption.regulation_provision,
                        "effective_date": exemption.effective_date.isoformat(),
                        "expiry_date": exemption.expiry_date.isoformat(),
                        "supporting_document_id": exemption.supporting_document_id,
                        "verified_by_user_id": exemption.verified_by_user_id,
                        "verified_at": exemption.verified_at.isoformat() if exemption.verified_at else None,
                    },
                },
                overridable=False,
                sort_order=spec.sort_order,
            ))
        return governed

    validation.build_findings = governed_build_findings
    _INSTALLED = True


__all__ = ["install_validation_policy"]
