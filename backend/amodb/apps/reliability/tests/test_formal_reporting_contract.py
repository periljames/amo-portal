from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from amodb.apps.reliability.formal_reporting import ALLOWED_TRANSITIONS, FormalReportCreate
from amodb.apps.reliability.formal_reporting_models import FormalPeriodType, FormalReportStatus
from amodb.apps.reliability.formal_reporting_profiles import (
    COMMON_PUBLICATION_RULES,
    COMMON_SOURCE_CODES,
    FORMAL_SECTIONS,
    PROFILE_VERSION,
    profile_definitions,
)


def _profile(code: str):
    return next(item for item in profile_definitions() if item["code"] == code)


def test_baseline_profiles_are_versioned_and_cover_full_formal_structure():
    definitions = profile_definitions()
    assert PROFILE_VERSION == "2026-08-07.1"
    assert {item["code"] for item in definitions} == {"KCAA", "EASA", "FAA", "OPERATOR"}
    assert len(FORMAL_SECTIONS) == 24
    assert len({item["code"] for item in FORMAL_SECTIONS}) == 24
    assert COMMON_SOURCE_CODES == [
        "AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "SB", "CS", "AS", "UR",
        "STRUCTURES", "RECURRING", "ECTM", "ADD",
    ]
    for definition in definitions:
        assert definition["required_sections"] == FORMAL_SECTIONS
        assert definition["historical_windows"] == [12, 24, 36]
        assert definition["source_manifest"]


def test_kcaa_profile_does_not_treat_2018_ac_as_current_2025_compliance():
    kcaa = _profile("KCAA")
    current = next(item for item in kcaa["requirements"] if item["requirement_key"] == "KCAA-CURRENT-REGULATORY-MAPPING")
    legacy = next(item for item in kcaa["requirements"] if item["requirement_key"] == "KCAA-AWS010D-PERIODIC-REPORT-CONTENT")

    assert current["obligation_status"] == "MANDATORY"
    assert current["evidence_rule"]["default_status"] == "GAP"
    assert current["completeness_rule"]["publication_blocking"] is True
    assert current["applicability_rule"]["manual_verification_required"] is True

    assert legacy["obligation_status"] == "ADVISORY"
    assert legacy["applicability_rule"]["legacy_guidance"] is True
    assert legacy["effective_date"] == date(2018, 7, 1)


def test_faa_profile_tracks_current_editorial_update_without_upgrading_guidance_to_regulation():
    faa = _profile("FAA")
    assert faa["effective_date"] == date(2026, 7, 9)
    assert "Editorial Update 2026-07-09" in faa["revision"]
    ac_requirements = [item for item in faa["requirements"] if item["source_reference"] == "AC 120-17B"]
    assert ac_requirements
    assert all(item["obligation_status"] == "ADVISORY" for item in ac_requirements)
    authority_gate = next(item for item in faa["requirements"] if item["requirement_key"] == "FAA-CFR-OPSPECS-APPLICABILITY")
    assert authority_gate["obligation_status"] == "MANDATORY"
    assert authority_gate["evidence_rule"]["default_status"] == "GAP"


def test_publication_rules_require_frozen_evidence_and_artifact_hashes():
    assert COMMON_PUBLICATION_RULES["block_mandatory_gap"] is True
    assert COMMON_PUBLICATION_RULES["block_unexplained_withheld"] is True
    assert COMMON_PUBLICATION_RULES["require_frozen_effectivity"] is True
    assert COMMON_PUBLICATION_RULES["require_data_cutoff"] is True
    assert COMMON_PUBLICATION_RULES["require_calculation_snapshot"] is True
    assert COMMON_PUBLICATION_RULES["require_source_manifest"] is True
    assert COMMON_PUBLICATION_RULES["require_html_hash"] is True
    assert COMMON_PUBLICATION_RULES["require_pdf_hash"] is True
    assert COMMON_PUBLICATION_RULES["exception_override_requires_governed_record"] is True


def test_published_report_can_only_be_superseded_or_withdrawn():
    assert ALLOWED_TRANSITIONS[FormalReportStatus.PUBLISHED.value] == {
        FormalReportStatus.SUPERSEDED.value,
        FormalReportStatus.WITHDRAWN.value,
    }
    assert ALLOWED_TRANSITIONS[FormalReportStatus.SUPERSEDED.value] == set()
    assert ALLOWED_TRANSITIONS[FormalReportStatus.WITHDRAWN.value] == set()


def test_formal_report_request_rejects_reverse_period():
    with pytest.raises(ValidationError):
        FormalReportCreate(
            profile_id="profile",
            report_number="REL-2026-001",
            title="Annual Reliability Programme Report",
            period_type=FormalPeriodType.ANNUAL,
            period_start=date(2026, 12, 31),
            period_end=date(2026, 1, 1),
        )


def test_formal_report_request_supports_half_year_and_annual_periods():
    half_year = FormalReportCreate(
        profile_id="profile",
        report_number="REL-2026-H1",
        title="Half-year Reliability Programme Review",
        period_type=FormalPeriodType.HALF_YEAR,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
    )
    annual = FormalReportCreate(
        profile_id="profile",
        report_number="REL-2026-ANNUAL",
        title="Annual Reliability Programme Report",
        period_type=FormalPeriodType.ANNUAL,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )
    assert half_year.period_type == FormalPeriodType.HALF_YEAR
    assert annual.period_type == FormalPeriodType.ANNUAL
