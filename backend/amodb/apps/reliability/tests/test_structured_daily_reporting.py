from datetime import date

import pytest
from pydantic import ValidationError

from amodb.apps.reliability import management_reporting as reports
from amodb.apps.reliability import structured_csv_import as csv_import
from amodb.apps.reliability import workbook_parity as wp


def test_structured_csv_template_covers_every_controlled_dataset():
    codes = list(wp.WorkbookDatasetCode)
    assert len(codes) == 16
    for code in codes:
        headers = csv_import.csv_headers(code)
        assert "event_date" in headers
        assert len(headers) == len(set(headers))
        required = {field.key for field in wp.DATASET_CATALOG[code].fields if field.required}
        assert required.issubset(headers)
        if code == wp.WorkbookDatasetCode.AI:
            assert "aircraft_serial_number" not in headers
        else:
            assert "aircraft_serial_number" in headers


def test_structured_csv_is_utf8_and_delimiter_bounded():
    assert csv_import._decode_csv("event_date,aircraft_serial_number\n2026-08-07,5Y-SLK\n".encode())
    assert csv_import._delimiter("data.csv", "a;b\n1;2\n", None) == ";"
    assert csv_import._delimiter("data.tsv", "a\tb\n1\t2\n", None) == "\t"
    with pytest.raises(ValueError):
        csv_import._delimiter("data.csv", "a,b", "colon")
    with pytest.raises(ValueError):
        csv_import._decode_csv(b"a,b\x00c")


def test_management_report_defaults_to_all_domains_and_bounds_windows():
    request = reports.ManagementReportRequest(period_start=date(2026, 1, 1), period_end=date(2026, 3, 31))
    assert len(reports._codes(request)) == 16
    assert request.bucket == "AUTO"
    with pytest.raises(ValidationError):
        reports.ManagementReportRequest(period_start=date(2026, 4, 1), period_end=date(2026, 3, 31))
    with pytest.raises(ValidationError):
        reports.ManagementReportRequest(period_start=date(2024, 1, 1), period_end=date(2026, 8, 1))


def test_management_html_helpers_are_print_safe_and_escape_evidence():
    chart = reports._svg_bar([{"label": "<ATA 32>", "count": 3}], "label", "count", "Events")
    assert "&lt;ATA 32&gt;" in chart
    assert "<svg" in chart
    card = reports._metric_card({"label": "Dispatch <reliability>", "value": 99.5, "unit": "%", "detail": "Controlled"})
    assert "Dispatch &lt;reliability&gt;" in card
    assert "99.500" in card
