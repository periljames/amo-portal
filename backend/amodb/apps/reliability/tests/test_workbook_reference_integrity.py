from decimal import Decimal

from amodb.apps.reliability import workbook_analysis_integrity as analysis
from amodb.apps.reliability import workbook_parity as wp
from amodb.apps.reliability import workbook_reference_import as reference_import


def test_actual_workbook_domains_are_controlled():
    expected = {"AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "SB", "CS", "AS", "UR", "STRUCTURES", "RECURRING", "ECTM", "ADD"}
    assert {code.value for code in wp.WorkbookDatasetCode} == expected
    assert set(definition.code.value for definition in wp.DATASET_CATALOG.values()) == expected


def test_ur_rates_are_exact_and_zero_events_do_not_divide_by_zero():
    definition = wp.DATASET_CATALOG[wp.WorkbookDatasetCode.UR]
    _, derived = wp._normalise_payload(definition, {
        "reporting_period": "2026-Q2",
        "fleet_variant": "DHC8-300",
        "component_description": "Example component",
        "part_number": "PN-1",
        "quantity_per_aircraft": 2,
        "unit_hours": "100",
        "unscheduled_removals": 1,
        "total_removals": 2,
    })
    assert derived["urr_per_1000_unit_hours"] == "5.000000"
    assert derived["mtbur_unit_hours"] == "200.000000"
    assert derived["trr_per_1000_unit_hours"] == "10.000000"
    assert derived["mtbr_unit_hours"] == "100.000000"

    _, zero = wp._normalise_payload(definition, {
        "reporting_period": "2026-Q2",
        "fleet_variant": "DHC8-300",
        "component_description": "Example component",
        "part_number": "PN-1",
        "quantity_per_aircraft": 2,
        "unit_hours": "100",
        "unscheduled_removals": 0,
        "total_removals": 0,
    })
    assert zero["urr_per_1000_unit_hours"] == "0.000000"
    assert zero["mtbur_unit_hours"] is None
    assert zero["mtbur_status"] == "NO_UNSCHEDULED_REMOVALS_IN_PERIOD"
    assert zero["mtbr_unit_hours"] is None


def test_exact_sample_sigma_and_workbook_reference_method():
    series = [{"period": f"2026-{month:02d}-01", "exact_value": str(value)} for month, value in enumerate(range(1, 13), start=1)]
    sample = analysis._sample_sigma(series[:3], Decimal("2"), Decimal("3"))
    assert sample["mean"] == Decimal("2")
    assert sample["sample_stddev"] == Decimal("1")
    workbook = analysis._workbook_compatible(series)
    assert workbook["sample_size"] == 12
    assert workbook["warning_level"] < workbook["alert_level"]


def test_workbook_profiles_match_actual_reference_sheet_sets():
    c208 = reference_import._profile_match("SAFARILINK-C208B-RP", ["ALRT. CALC", "Data Type Index", "AU", "AI", "FI", "SB", "SR", "OS", "RM", "SM", "PM"])
    dhc8 = reference_import._profile_match("SAFARILINK-DHC8-RP", ["ALRT. CALC (HRS)", "ALRT. CALC", "UR", "Data Type Index", "AU", "AI", "FI", "OS", "PM", "SM", "RM", "SB", "CS", "AS", "SR"])
    assert c208["matched"] is True
    assert dhc8["matched"] is True
