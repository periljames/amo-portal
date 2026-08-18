from __future__ import annotations

from io import BytesIO

import pytest
from sqlalchemy import select

from amodb.apps.accounts import models as account_models
from amodb.apps.training.courses_import import import_courses_rows, parse_courses_sheet
from amodb.apps.training.models import TrainingCourse, TrainingRequirement


def _seed_amo(db):
    amo = account_models.AMO(
        id="amo-training-1",
        amo_code="AMO-TRN",
        name="Training AMO",
        login_slug="amo-training",
        is_active=True,
    )
    db.add(amo)
    db.commit()
    return amo


def _ensure_import_tables(db) -> None:
    TrainingCourse.__table__.create(bind=db.bind, checkfirst=True)
    TrainingRequirement.__table__.create(bind=db.bind, checkfirst=True)


def _xlsx_bytes(sheet_name: str, headers: list[str], rows: list[list[object]]) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_courses_sheet_rejects_wrong_sheet_and_unknown_headers():
    good_headers = [
        "CourseID",
        "CourseName",
        "FrequencyMonths",
        "Status",
        "Category",
        "Mandatory",
        "Scope",
        "Reference",
    ]
    payload = _xlsx_bytes("Wrong", good_headers, [])
    with pytest.raises(ValueError) as exc_info:
        parse_courses_sheet(payload, filename="COURSES.xlsx", sheet_name="Courses")
    assert "Sheet 'Courses' not found." in str(exc_info.value)

    bad_headers = good_headers.copy()
    bad_headers[0] = "UnknownCourseField"
    payload = _xlsx_bytes("Courses", bad_headers, [])
    with pytest.raises(ValueError) as exc_info:
        parse_courses_sheet(payload, filename="COURSES.xlsx", sheet_name="Courses")
    assert "Unsupported course import header" in str(exc_info.value)


def test_courses_import_contract_and_normalization(db_session):
    _ensure_import_tables(db_session)
    amo = _seed_amo(db_session)
    rows = [
        {
            "row_number": 2,
            "CourseID": "1510-INIT",
            "CourseName": "Composite Structures Inspection - Familiarisation",
            "FrequencyMonths": "",
            "Status": "Initial",
            "Category": "Maintenance",
            "Mandatory": "",
            "Scope": "",
            "Reference": "MTM 2.5",
        },
        {
            "row_number": 3,
            "CourseID": "1510-REF",
            "CourseName": "Composite Structures Inspection - Familiarisation",
            "FrequencyMonths": 24,
            "Status": "Recurrent",
            "Category": "Maintenance",
            "Mandatory": "Yes",
            "Scope": "All Staff",
            "Reference": "MPM 1.3.7.3",
        },
        {
            "row_number": 4,
            "CourseID": "PT6A-INIT",
            "CourseName": "PT6A\nINIT  ",
            "FrequencyMonths": None,
            "Status": "One_Off",
            "Category": "",
            "Mandatory": "No",
            "Scope": "",
            "Reference": "",
        },
    ]
    result = import_courses_rows(db_session, amo_id=amo.id, rows=rows, dry_run=False)
    assert result.created_courses == 3
    assert result.skipped_rows == 0

    saved = db_session.execute(
        select(
            TrainingCourse.__table__.c.course_id,
            TrainingCourse.__table__.c.course_name,
            TrainingCourse.__table__.c.frequency_months,
            TrainingCourse.__table__.c.status,
            TrainingCourse.__table__.c.scope,
            TrainingCourse.__table__.c.regulatory_reference,
            TrainingCourse.__table__.c.is_mandatory,
            TrainingCourse.__table__.c.is_active,
        ).order_by(TrainingCourse.__table__.c.course_id.asc())
    ).all()

    assert [r.course_id for r in saved] == ["1510-INIT", "1510-REF", "PT6A-INIT"]
    assert saved[0].course_name == "Composite Structures Inspection - Familiarisation"
    assert saved[1].course_name == "Composite Structures Inspection - Familiarisation"
    assert saved[2].course_name == "PT6A INIT"
    assert saved[0].frequency_months is None
    assert saved[1].frequency_months == 24
    assert saved[0].is_mandatory is False
    assert saved[1].is_mandatory is True
    assert saved[2].is_mandatory is False
    assert saved[1].scope == "All Staff"
    assert saved[0].regulatory_reference == "MTM 2.5"
    assert saved[1].regulatory_reference == "MPM 1.3.7.3"
    assert all(r.is_active is True for r in saved)


def test_courses_import_rejects_duplicate_course_id_and_invalid_tokens(db_session):
    _ensure_import_tables(db_session)
    amo = _seed_amo(db_session)
    rows = [
        {
            "row_number": 2,
            "CourseID": "QMS-REF",
            "CourseName": "QMS Recurrent",
            "FrequencyMonths": 36,
            "Status": "Initial",
            "Category": "Quality",
            "Mandatory": "Yes",
            "Scope": "",
            "Reference": "",
        },
        {
            "row_number": 3,
            "CourseID": "QMS-REF",
            "CourseName": "QMS Recurrent Copy",
            "FrequencyMonths": "",
            "Status": "Recurrent",
            "Category": "Quality",
            "Mandatory": "",
            "Scope": "",
            "Reference": "",
        },
        {
            "row_number": 4,
            "CourseID": "SMS-REF",
            "CourseName": "SMS Recurrent",
            "FrequencyMonths": "abc",
            "Status": "One_Off",
            "Category": "Safety",
            "Mandatory": "",
            "Scope": "",
            "Reference": "",
        },
        {
            "row_number": 5,
            "CourseID": "AVSEC-INIT",
            "CourseName": "AVSEC Initial",
            "FrequencyMonths": "",
            "Status": "Active",
            "Category": "Safety",
            "Mandatory": "MAYBE",
            "Scope": "",
            "Reference": "",
        },
    ]
    result = import_courses_rows(db_session, amo_id=amo.id, rows=rows, dry_run=True)
    reasons = [issue.reason for issue in result.issues]
    assert any("Duplicate CourseID inside import file." == r for r in reasons)
    assert any("FrequencyMonths must be an integer or blank" in r for r in reasons)
    assert any("Status/CourseType must be one of: Initial, Recurrent, One_Off" in r for r in reasons)

    mandatory_issue = import_courses_rows(
        db_session,
        amo_id=amo.id,
        rows=[
            {
                "row_number": 9,
                "CourseID": "AC-REL",
                "CourseName": "Aircraft Reliability ",
                "FrequencyMonths": "",
                "Status": "Initial",
                "Category": "",
                "Mandatory": "MAYBE",
                "Scope": "",
                "Reference": "",
            }
        ],
        dry_run=True,
    )
    assert mandatory_issue.skipped_rows == 1
    assert mandatory_issue.issues[0].row_number == 9
    assert "Mandatory must be Yes/No (or blank)" in mandatory_issue.issues[0].reason


def test_courses_workbook_fixture_dry_run_and_live_import(db_session):
    _ensure_import_tables(db_session)
    amo = _seed_amo(db_session)
    headers = [
        "CourseID",
        "CourseName",
        "FrequencyMonths",
        "Status",
        "Category",
        "Mandatory",
        "Scope",
        "Reference",
    ]
    rows = [
        ["1510-INIT", "Composite Structures Inspection - Familiarisation", "", "Initial", "Maintenance", "", "", "MTM 2.5"],
        ["1510-REF", "Composite Structures Inspection - Familiarisation", 24, "Recurrent", "Maintenance", "Yes", "All Staff", "MPM 1.3.7.3"],
        ["PT6A-REF", "PT6A\nREF ", "", "One_Off", "", "", "", ""],
    ]
    workbook = _xlsx_bytes("Courses", headers, rows)

    parsed_rows = parse_courses_sheet(workbook, filename="COURSES.xlsx", sheet_name="Courses")
    assert len(parsed_rows) == 3

    dry = import_courses_rows(db_session, amo_id=amo.id, rows=parsed_rows, dry_run=True)
    assert dry.dry_run is True
    assert dry.created_courses == 3
    assert dry.skipped_rows == 0
    assert db_session.query(TrainingCourse).count() == 0

    live = import_courses_rows(db_session, amo_id=amo.id, rows=parsed_rows, dry_run=False)
    assert live.dry_run is False
    assert live.created_courses == 3
    assert live.skipped_rows == 0
    saved = db_session.execute(
        select(TrainingCourse.__table__.c.course_name).order_by(TrainingCourse.__table__.c.course_id.asc())
    ).all()
    assert [r.course_name for r in saved] == [
        "Composite Structures Inspection - Familiarisation",
        "Composite Structures Inspection - Familiarisation",
        "PT6A REF",
    ]
