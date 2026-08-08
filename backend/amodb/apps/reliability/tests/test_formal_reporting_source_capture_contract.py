from __future__ import annotations

from . import test_formal_reporting_contract  # noqa: F401
from amodb.apps.reliability.formal_reporting_source_capture import (
    DASHBOARD_SOURCE_FAMILIES,
    SOURCE_KIND,
)


def test_formal_source_contract_covers_every_dashboard_input_family():
    assert DASHBOARD_SOURCE_FAMILIES == {
        "aircraft",
        "events",
        "utilisation",
        "deferrals",
        "fracas_cases",
        "fracas_actions",
        "fracas_lifecycles",
        "effectiveness_reviews",
        "engine_statuses",
        "engine_snapshots",
        "removals",
        "shop_visits",
        "oil_rates",
        "sources",
        "batches",
        "data_quality",
        "metric_definitions",
    }
    assert DASHBOARD_SOURCE_FAMILIES <= SOURCE_KIND.keys()
    assert len(set(SOURCE_KIND.values())) == len(SOURCE_KIND)
    assert all(len(value) <= 40 for value in SOURCE_KIND.values())


def test_workbook_provenance_is_retained_in_addition_to_dashboard_inputs():
    assert SOURCE_KIND["workbook"] == "WORKBOOK_RECORD"
    assert "workbook" not in DASHBOARD_SOURCE_FAMILIES
