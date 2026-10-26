from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.quality.amo_compliance_policy import (
    RULES, assert_disposition_due, policy_catalogue, prepare_retention,
    retention_assessment, validate_retention_extensions,
)
from amodb.apps.quality.provider_qualification_router import PolicyWrite


def facts(**events):
    return {"compliance_retention": {"events": events}}


def test_company_three_year_floor_exceeds_verified_two_year_regulatory_minimum():
    rule = RULES["MAINTENANCE_RECORDS"]
    assert rule.years == 3 and rule.regulatory_minimum_years == 2
    result = retention_assessment(rule.code, facts(release_signed_at="2024-02-29T12:30:00Z"))
    assert result["minimum_until"] == "2027-02-28T12:30:00+00:00"


def test_unknown_withdrawal_preserves_logbooks_and_ignores_upload_age():
    due, metadata = prepare_retention("LOGBOOKS", facts(uploaded_at="2000-01-01"), "2020-01-01")
    assert due is None
    assert metadata["retention_assessment"]["unresolved"] == ["permanent_withdrawal_at"]


def test_longest_linked_company_contractual_and_operator_requirement_wins():
    metadata = facts(release_signed_at="2023-01-01", contract_ended_at="2026-10-22")
    metadata["compliance_retention"].update(classes=["MAINTENANCE_RECORDS", "OPERATOR_CONTRACT_RECORDS"], contractual_until="2030-03-01")
    result = retention_assessment("MAINTENANCE_RECORDS", metadata)
    assert result["effective_until"].startswith("2030-03-01")
    with pytest.raises(HTTPException):
        retention_assessment("MAINTENANCE_RECORDS", metadata, requested_until="2029-01-01")


def test_ninety_day_summary_rule_never_discards_unique_maintenance_evidence():
    metadata = facts(permanent_withdrawal_at="2026-01-01T00:00:00Z")
    assert retention_assessment("STATUS_SUMMARIES", metadata)["effective_until"] is None
    metadata["compliance_retention"]["underlying_records_separately_retained"] = True
    assert retention_assessment("STATUS_SUMMARIES", metadata)["effective_until"] == "2026-04-01T00:00:00+00:00"


@pytest.mark.parametrize("code,event,years", [
    ("WORKSHOP_RECORDS", "release_signed_at", 3), ("TECHNICAL_LOGS", "last_entry_at", 3),
    ("CALIBRATION_CERTIFICATES", "tool_scrapped_at", 2), ("SCRAP_REGISTER", "scrapped_at", 7),
    ("PERSONNEL_RECORDS", "employment_ended_at", 2), ("AUTHORIZATION_HISTORY", "authorization_withdrawn_at", 2),
    ("OCCURRENCE_RECORDS", "permanent_withdrawal_at", 2), ("QMS_AUDIT_RECORDS", "qms_retention_event_at", 5),
])
def test_record_class_uses_its_own_event(code, event, years):
    result = retention_assessment(code, facts(**{event: "2020-03-01T12:00:00Z"}))
    assert result["effective_until"] == f"{2020 + years}-03-01T12:00:00+00:00"


@pytest.mark.parametrize("extension", [
    {"extensions_years": {"MAINTENANCE_RECORDS": 2}},
    {"extensions_days": {"STATUS_SUMMARIES": 89}},
    {"extensions_years": {"LOGBOOKS": True}},
    {"extensions_years": {"UNKNOWN": 10}}, {"allow_early_disposal": True},
])
def test_tenant_options_cannot_lower_or_replace_baseline(extension):
    with pytest.raises(HTTPException):
        validate_retention_extensions(extension)


def test_new_extension_applies_to_old_retention_record_before_execution():
    row = SimpleNamespace(retention_class="MAINTENANCE_RECORDS", metadata_json=facts(release_signed_at="2020-01-01T00:00:00Z"), retention_until=datetime(2023, 1, 1, tzinfo=timezone.utc), legal_hold=False)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert_disposition_due(row, now=now)
    with pytest.raises(HTTPException) as error:
        assert_disposition_due(row, now=now, extensions={"extensions_years": {"MAINTENANCE_RECORDS": 5}})
    assert error.value.status_code == 409


@pytest.mark.parametrize("hold", ["preservation_hold", "investigation_open", "requirements_unconfirmed"])
def test_preservation_obligations_block_even_expired_dates(hold):
    metadata = facts(release_signed_at="2000-01-01")
    metadata["compliance_retention"][hold] = True
    row = SimpleNamespace(retention_class="MAINTENANCE_RECORDS", metadata_json=metadata, retention_until=None, legal_hold=False)
    with pytest.raises(HTTPException):
        assert_disposition_due(row)


def test_unclassified_and_unconfirmed_agreement_schedules_are_preserved():
    for code in ("STANDARD", "MAINTENANCE_AGREEMENTS"):
        row = SimpleNamespace(retention_class=code, metadata_json=facts(quality_retention_determined_at="2000-01-01"), retention_until=None, legal_hold=False)
        with pytest.raises(HTTPException):
            assert_disposition_due(row)


def test_annual_supplier_surveillance_is_default_and_cannot_be_extended():
    assert PolicyWrite(reason="Annual policy baseline").surveillance_days == 365
    assert PolicyWrite(reason="Risk based surveillance", surveillance_days=90).surveillance_days == 90
    for value in (None, 366, 3650):
        with pytest.raises(ValidationError):
            PolicyWrite(reason="Policy cannot waive annual review", surveillance_days=value)
    assert policy_catalogue()["contracting"]["approved_amo_required"]


def test_series_period_uses_the_actual_event_and_never_upload_age():
    until, _ = prepare_retention("MAINTENANCE_RECORDS", facts(release_signed_at="2020-02-29"), series_years=7)
    assert until.date().isoformat() == "2027-02-28"
    until, metadata = prepare_retention("LOGBOOKS", facts(), series_years=7)
    assert until is None and metadata["retention_assessment"]["unresolved"]
    until, _ = prepare_retention("MAINTENANCE_RECORDS", facts(release_signed_at="2020-01-01"), series_years=1,
        extensions={"extensions_years":{"MAINTENANCE_RECORDS":5}})
    assert until.date().isoformat() == "2025-01-01"


def test_provider_profile_cannot_bypass_the_annual_qualification_policy():
    from amodb.apps.quality.provider_governance_router import ProviderProfilePatch
    with pytest.raises(ValidationError):
        ProviderProfilePatch(expected_version=1, review_interval_days=366, reason="Cannot weaken annual review")


def test_reclassification_cannot_drop_an_existing_service_life_obligation():
    from amodb.apps.quality.amo_compliance_policy import reclassification_metadata
    metadata = reclassification_metadata("LOGBOOKS", facts(), facts(release_signed_at="2000-01-01"))
    result = retention_assessment("MAINTENANCE_RECORDS", metadata)
    assert "LOGBOOKS" in result["classes"] and result["effective_until"] is None
    metadata = reclassification_metadata("PERMANENT", {}, facts(release_signed_at="2000-01-01"))
    result = retention_assessment("MAINTENANCE_RECORDS", metadata)
    assert "PERMANENT" in result["classes"] and result["effective_until"] is None


def test_audit_archive_policies_cannot_disable_preservation_controls_or_five_year_floor():
    from amodb.apps.quality.audit_archive_governance_router import RetentionPolicyCreate
    baseline = dict(retention_class="QMS_AUDIT_RECORDS", retention_start_event="FOLLOW_UP_COMPLETE",
        duration_days=1827, governing_basis="MOPM 3.3 and QMSM 4.11", disposition_mode="PRESERVE_METADATA_DELETE_PACKAGE")
    assert RetentionPolicyCreate(**baseline).duration_days == 1827
    for change in ({"duration_days": 1}, {"duration_days": 1825}, {"review_before_disposition": False}, {"legal_hold_supported": False}):
        with pytest.raises(ValidationError):
            RetentionPolicyCreate(**{**baseline, **change})


def test_existing_short_audit_package_is_still_held_until_five_calendar_years(monkeypatch):
    from amodb.apps.quality import audit_archive_governance_router as archive
    monkeypatch.setattr(archive, "_utcnow", lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    manifest = SimpleNamespace(retention_start_at=datetime(2020, 1, 1, tzinfo=timezone.utc), retention_due_at=datetime(2020, 2, 1, tzinfo=timezone.utc))
    policy = SimpleNamespace(indefinite=False, disposition_mode="PRESERVE_METADATA_DELETE_PACKAGE")
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    with pytest.raises(HTTPException) as error:
        archive._assert_mopm_archive_due(db,manifest=manifest,policy=policy,amo_id="tenant-a",audit_id="audit")
    assert error.value.status_code == 409
