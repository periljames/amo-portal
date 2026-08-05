from amodb.apps.aircraft_induction.ingestion import classify_dataset, fingerprint_dataset, normalize_header


def test_header_normalisation_separates_source_layout_from_aircraft_type():
    assert normalize_header("Manufacturer Serial Number") == "serial_number"
    assert normalize_header("A/C Reg") == "registration"
    assert normalize_header("TTAF") == "total_hours"


def test_fingerprint_is_stable_when_source_column_order_changes():
    first = fingerprint_dataset(
        "WINAIR",
        "UTILISATION",
        ["date", "techlog_no", "total_hours", "total_cycles"],
        "Flight Log",
    )
    second = fingerprint_dataset(
        "WINAIR",
        "UTILISATION",
        ["total_cycles", "date", "total_hours", "techlog_no"],
        "Flight Log",
    )
    assert first == second


def test_sheet_and_headers_classify_independent_datasets():
    assert classify_dataset("HOURS", ["date", "techlog_no", "total_hours", "total_cycles"]) == "UTILISATION"
    assert classify_dataset("Airframe AD Status", ["ad_number", "compliance_status"]) == "AD_STATUS"
    assert classify_dataset("HARD TIME", ["position", "part_number", "serial_number", "life_limit"]) in {"COMPONENTS", "LLP_STATUS"}


def test_explicit_dataset_selection_is_validated():
    assert classify_dataset("Any sheet", ["unknown"], "CONFIGURATION") == "CONFIGURATION"
