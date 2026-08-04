from __future__ import annotations

from io import BytesIO

import pytest

from amodb.apps.training.courses_import import parse_courses_sheet


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Courses"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_accepts_legacy_course_type_header_from_courses_workbook():
    workbook = _xlsx_bytes(
        [
            "CourseID",
            "CourseName",
            "FrequencyMonths",
            "CourseType",
            "Category",
            "Mandatory",
            "Scope",
            "Reference",
        ],
        [["AVSEC-REF", "Aviation Security (Refresher)", 24, "Recurrent", "Safety", "Yes", "All Staff", "KCAR"]],
    )

    rows = parse_courses_sheet(workbook, filename="COURSES.xlsx")

    assert rows == [
        {
            "row_number": 2,
            "CourseID": "AVSEC-REF",
            "CourseName": "Aviation Security (Refresher)",
            "FrequencyMonths": 24,
            "Status": "Recurrent",
            "Category": "Safety",
            "Mandatory": "Yes",
            "Scope": "All Staff",
            "Reference": "KCAR",
        }
    ]


def test_accepts_portal_course_csv_export_schema_for_round_trip_import():
    payload = (
        "course_id,course_name,status,category,scope,mandatory,frequency_months,regulatory_reference,active\n"
        "AVSEC-INIT,Aviation Security (Initial),Initial,OTHER,,YES,,,YES\n"
        "AVSEC-REF,Aviation Security (Refresher),Recurrent,OTHER,,NO,24,,NO\n"
    ).encode("utf-8")

    rows = parse_courses_sheet(payload, filename="training-courses-safarilink.csv")

    assert rows[0]["CourseID"] == "AVSEC-INIT"
    assert rows[0]["Status"] == "Initial"
    assert rows[0]["Active"] == "YES"
    assert rows[1]["FrequencyMonths"] == "24"
    assert rows[1]["Reference"] == ""
    assert rows[1]["Active"] == "NO"


def test_rejects_unknown_headers_with_actionable_message():
    workbook = _xlsx_bytes(
        ["CourseID", "CourseName", "FrequencyMonths", "CourseType", "Category", "Mandatory", "Scope", "UnknownField"],
        [],
    )

    with pytest.raises(ValueError) as exc_info:
        parse_courses_sheet(workbook, filename="COURSES.xlsx")

    message = str(exc_info.value)
    assert "Unsupported course import header" in message
    assert "CourseType" in message
    assert "portal CSV export labels" in message
