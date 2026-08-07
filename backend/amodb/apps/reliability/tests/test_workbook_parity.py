from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import APIRouter, HTTPException

from amodb.apps.reliability import workbook_parity
from amodb.apps.reliability import workbook_parity_defaults
from amodb.apps.reliability import workbook_parity_statistics

EXPECTED_DATASETS = {"AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "SB", "CS", "AS", "UR", "STRUCTURES", "RECURRING", "ECTM", "ADD"}


def test_catalog_covers_every_required_workbook_register():
    assert {code.value for code in workbook_parity.DATASET_CATALOG} == EXPECTED_DATASETS
    for definition in workbook_parity.DATASET_CATALOG.values():
        assert definition.name
        assert definition.workbook_sheet_names
        assert definition.fields
        assert len({field.key for field in definition.fields}) == len(definition.fields)
        assert any(field.required for field in definition.fields)


def test_aircraft_utilisation_contract_has_aircraft_engine_and_apu_exposure():
    keys = {field.key for field in workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.AU].fields}
    assert {"flight_hours", "flight_cycles", "landings", "engine_1_hours", "engine_1_cycles", "engine_2_hours", "engine_2_cycles", "apu_hours", "apu_cycles", "source_reference"} <= keys


def test_flight_interruption_rates_retain_evidence_and_withhold_missing_denominators():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.FI]
    normalised, derived = workbook_parity._normalise_payload(definition, {
        "reporting_period": "2026-08-01",
        "interruption_type": "TECHNICAL_DELAY",
        "departures": 100,
        "technical_delays": 2,
        "delay_minutes": 46,
        "dispatch_successes": 98,
        "scheduled_departures": 102,
        "completed_departures": 100,
        "ata_interruptions": 2,
        "flight_hours_denominator": "240.500",
        "defect_description": "Starter-generator dispatch interruption.",
    })
    assert normalised["flight_hours_denominator"] == "240.500"
    assert derived["dispatch_reliability_pct"] == "98.000"
    assert derived["dispatch_reliability_numerator"] == 98
    assert derived["dispatch_reliability_denominator"] == 100
    assert derived["schedule_completion_pct"] == "98.039"
    assert derived["ata_interruption_rate_per_100_fh"] == "0.832"

    _, withheld = workbook_parity._normalise_payload(definition, {
        "reporting_period": "2026-08-01",
        "interruption_type": "TECHNICAL_DELAY",
        "departures": 0,
        "dispatch_successes": 0,
        "ata_interruptions": 1,
        "defect_description": "No valid exposure available.",
    })
    assert withheld["dispatch_reliability_pct"] is None
    assert withheld["ata_interruption_rate_per_100_fh"] is None
    assert "denominator" in withheld["dispatch_reliability_withheld_reason"].lower()


def test_oos_derives_downtime_availability_and_validates_chronology():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.OOS]
    normalised, derived = workbook_parity._normalise_payload(definition, {"start_at": "2026-08-01T06:00:00+00:00", "end_at": "2026-08-01T12:00:00+00:00", "reason_category": "TECHNICAL", "maintenance_action": "Replaced failed starter-generator.", "scheduled_available_hours": "24.000"})
    assert normalised["reason_category"] == "TECHNICAL"
    assert derived == {"downtime_hours": "6.000", "available_hours": "18.000", "availability_pct": "75.000"}
    with pytest.raises(HTTPException, match="cannot precede"):
        workbook_parity._normalise_payload(definition, {"start_at": "2026-08-02T12:00:00+00:00", "end_at": "2026-08-02T06:00:00+00:00", "reason_category": "TECHNICAL", "maintenance_action": "Invalid chronology."})


def test_recurring_defect_requires_actual_recurrence_and_ordered_dates():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.RECURRING]
    base = {"repeat_key": "ATA21-PACK-VALVE", "first_seen": "2026-01-01", "last_seen": "2026-02-01", "origin": "PIREP", "defect_description": "Pack valve failed to regulate.", "occurrence_count": 2, "recurrence_window_days": 31, "status": "UNDER_INVESTIGATION"}
    normalised, _ = workbook_parity._normalise_payload(definition, base)
    assert normalised["occurrence_count"] == 2
    with pytest.raises(HTTPException, match="at least two"):
        workbook_parity._normalise_payload(definition, {**base, "occurrence_count": 1})
    with pytest.raises(HTTPException, match="cannot precede"):
        workbook_parity._normalise_payload(definition, {**base, "first_seen": "2026-03-01", "last_seen": "2026-02-01"})


def test_unscheduled_removal_requires_failure_reason_and_exact_life_values():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.RM]
    payload = {"removed_at": "2026-08-01T08:00:00+00:00", "component_description": "Starter-generator", "off_part_number": "23085-001", "off_serial_number": "SG-1001", "removal_type": "UNSCHEDULED", "reason_code": "NO OUTPUT", "hours_at_removal": "1245.375", "cycles_at_removal": 1811}
    normalised, _ = workbook_parity._normalise_payload(definition, payload)
    assert normalised["hours_at_removal"] == "1245.375"
    assert normalised["cycles_at_removal"] == 1811
    with pytest.raises(HTTPException, match="requires a failure mode"):
        workbook_parity._normalise_payload(definition, {**payload, "reason_code": ""})
    with pytest.raises(HTTPException, match="whole number"):
        workbook_parity._normalise_payload(definition, {**payload, "cycles_at_removal": "1811.5"})


def test_shop_report_enforces_chronology_and_exclusive_fault_outcome():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.SR]
    payload = {
        "component_description": "Starter-generator",
        "component_part_number": "23085-001",
        "component_serial_number": "SG-1001",
        "shop_visit_reference": "SV-2026-0042",
        "induction_date": "2026-08-01",
        "release_date": "2026-08-08",
        "confirmed_fault": True,
        "no_fault_found": False,
        "finding_description": "Open field winding confirmed.",
        "corrective_action": "Rewound and bench tested.",
        "supplier": "Approved Repair Agency",
        "release_document_reference": "EASA-F1-0042",
    }
    _, derived = workbook_parity._normalise_payload(definition, payload)
    assert derived["shop_turnaround_days"] == 7
    with pytest.raises(HTTPException, match="cannot be both"):
        workbook_parity._normalise_payload(definition, {**payload, "no_fault_found": True})
    with pytest.raises(HTTPException, match="cannot precede"):
        workbook_parity._normalise_payload(definition, {**payload, "release_date": "2026-07-31"})


def test_ectm_contract_includes_numeric_and_qualitative_engine_health_fields():
    keys = {field.key for field in workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.ECTM].fields}
    assert {"itt_c", "ng_pct", "nh_pct", "fuel_flow", "oil_pressure", "oil_temperature", "vibration", "oil_analysis_status", "oil_analysis_reference", "borescope_status", "borescope_reference", "trend_status", "analyst_comments", "oem_recommendation", "action_required"} <= keys


def test_add_deferral_contract_derives_closure_duration_and_rejects_bad_dates():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.ADD]
    payload = {
        "deferral_type": "MEL",
        "tech_log_reference": "TL-2481",
        "defect_description": "Weather radar inoperative.",
        "occurrence_date": "2026-08-01",
        "mel_cdl_reference": "MEL 34-41-01",
        "category": "C",
        "expiry_date": "2026-08-11",
        "rectification_date": "2026-08-08",
        "status": "RECTIFIED",
        "closure_reference": "WO-2026-4412",
    }
    _, derived = workbook_parity._normalise_payload(definition, payload)
    assert derived["closure_duration_days"] == 7
    with pytest.raises(HTTPException, match="expiry cannot precede"):
        workbook_parity._normalise_payload(definition, {**payload, "expiry_date": "2026-07-31"})
    with pytest.raises(HTTPException, match="Rectification date cannot precede"):
        workbook_parity._normalise_payload(definition, {**payload, "rectification_date": "2026-07-31"})


def test_default_mapping_profiles_have_full_field_coverage():
    contract = workbook_parity_defaults.mapping_contract()
    assert set(contract["profiles"]) == {"SAFARILINK-C208B-RP", "SAFARILINK-DHC8-RP", "GENERIC-ANALYSIS-TEMPLATE"}
    for profile in contract["profiles"].values():
        assert set(profile) == EXPECTED_DATASETS
        for dataset in profile.values():
            assert dataset["coverage_pct"] == 100.0
            assert dataset["missing_fields"] == []
            assert dataset["missing_required_fields"] == []


def test_default_mapping_rows_are_unique_per_profile_sheet_and_column():
    keys = [(row["profile_code"], row["dataset_code"], row["source_sheet"], row["source_column"]) for row in workbook_parity_defaults.DEFAULT_MAPPING_ROWS]
    assert len(keys) == len(set(keys))
    assert all(row["aliases"] for row in workbook_parity_defaults.DEFAULT_MAPPING_ROWS)


def test_report_layouts_cover_operator_output_and_type_specific_sections():
    contract = workbook_parity_defaults.layout_contract()
    operator = contract["layouts"]["OPERATOR-RP"]
    assert set(operator["datasets"]) == EXPECTED_DATASETS
    assert operator["missing_datasets"] == []
    assert operator["has_statistical_alerts"] is True
    assert {"AU", "FI", "PM", "RM", "SR", "OOS", "RECURRING", "ECTM", "ADD"} <= set(contract["layouts"]["C208B-RP"]["datasets"])
    assert {"AU", "AI", "FI", "SM", "SR", "STRUCTURES", "RM", "OOS", "RECURRING", "ECTM", "ADD"} <= set(contract["layouts"]["DHC8-RP"]["datasets"])


def test_statistical_series_contains_zero_count_periods():
    assert workbook_parity_statistics.complete_bucket_sequence(date(2026, 1, 1), date(2026, 4, 30), "MONTH") == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]
    levels = workbook_parity_statistics.calculate_levels([{"period": "2026-01-01", "value": 0.0}, {"period": "2026-02-01", "value": 2.0}, {"period": "2026-03-01", "value": 0.0}], Decimal("1"), Decimal("2"))
    assert levels["sample_size"] == 3
    assert float(levels["mean"]) == pytest.approx(2 / 3)
    assert float(levels["sample_stddev"]) == pytest.approx(1.1547005383792517)
    assert levels["alert_level"] > levels["warning_level"] > levels["mean"]


def test_router_registers_every_workbook_parity_surface():
    router = APIRouter(prefix="/reliability")
    workbook_parity.register(router)
    workbook_parity_defaults.register(router)
    workbook_parity_statistics.register(router)
    paths = {route.path for route in router.routes}
    assert {"/reliability/workbook-parity/catalog", "/reliability/workbook-parity/records", "/reliability/workbook-parity/records/{record_id}/approve", "/reliability/workbook-parity/records/{record_id}/close", "/reliability/workbook-parity/oos-metrics", "/reliability/workbook-parity/statistical-alerts", "/reliability/workbook-parity/statistical-alerts/calculate", "/reliability/workbook-parity/mappings", "/reliability/workbook-parity/mappings/seed-defaults", "/reliability/workbook-parity/parity", "/reliability/workbook-parity/contracts", "/reliability/workbook-parity/report-layouts", "/reliability/workbook-parity/report-layouts/seed", "/reliability/workbook-parity/reports/render", "/reliability/workbook-parity/reports", "/reliability/workbook-parity/reports/{report_id}/html"} <= paths
