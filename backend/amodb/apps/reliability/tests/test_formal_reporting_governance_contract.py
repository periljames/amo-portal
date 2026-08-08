from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from amodb.apps.reliability.formal_reporting_governance import (
    AMP_CHANGE_TYPES,
    AMP_FLOW,
    DISTRIBUTABLE_STATUSES,
    AmpRecommendationCreate,
    FormalDistributionCreate,
    ReportingScheduleCreate,
)
from amodb.apps.reliability.formal_reporting_models import AmpRecommendationStatus, FormalPeriodType, FormalReportStatus


def test_amp_recommendation_flow_matches_governed_lifecycle():
    assert AMP_FLOW == [
        "IDENTIFIED",
        "ANALYSIS",
        "RECOMMENDED",
        "TECHNICAL_REVIEW",
        "QUALITY_REVIEW",
        "AUTHORITY_APPROVAL_REQUIRED",
        "APPROVED",
        "IMPLEMENTED",
        "EFFECTIVENESS_MONITORING",
        "CLOSED",
    ]
    assert AMP_FLOW == [item.value for item in AmpRecommendationStatus]


def test_amp_recommendation_requires_evidence_and_proposed_change():
    with pytest.raises(ValidationError):
        AmpRecommendationCreate(
            title="Escalate inspection interval",
            summary="Reliability evidence indicates stable performance across the controlled period.",
            change_type="TASK_ESCALATION",
            source_evidence=[],
            proposed_change={},
        )


def test_amp_recommendation_rejects_unknown_change_type():
    with pytest.raises(ValidationError):
        AmpRecommendationCreate(
            title="Unknown change",
            summary="A recommendation must use a governed maintenance-programme change class.",
            change_type="AUTOMATIC_AMP_MUTATION",
            source_evidence=[{"kind": "FORMAL_REPORT", "id": "report"}],
            proposed_change={"interval": "changed"},
        )
    assert "AUTOMATIC_AMP_MUTATION" not in AMP_CHANGE_TYPES


def test_schedule_rejects_reverse_period():
    with pytest.raises(ValidationError):
        ReportingScheduleCreate(
            obligation_code="H1",
            name="Half-year Reliability review",
            period_type=FormalPeriodType.HALF_YEAR,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 6, 30),
            due_date=date(2026, 7, 31),
        )


def test_distribution_requires_controlled_recipient():
    with pytest.raises(ValidationError):
        FormalDistributionCreate()
    payload = FormalDistributionCreate(recipient_role="QUALITY_MANAGER")
    assert payload.channel == "PORTAL"


def test_superseded_reports_remain_retained_but_only_published_is_new_distribution_target():
    assert DISTRIBUTABLE_STATUSES == {
        FormalReportStatus.PUBLISHED.value,
        FormalReportStatus.SUPERSEDED.value,
    }
    assert FormalReportStatus.WITHDRAWN.value not in DISTRIBUTABLE_STATUSES
