from __future__ import annotations

from datetime import date

from amodb.apps.training.workbook_import import WORKBOOK_SHEETS, _course_payload, _default_frequency_months, _person_payload, _workbook_params


def test_training_tracker_operational_and_derived_sheets_are_explicitly_mapped():
    operational = {name for name, config in WORKBOOK_SHEETS.items() if config["operational"]}
    derived = {name for name, config in WORKBOOK_SHEETS.items() if not config["operational"]}

    assert operational == {
        "People",
        "Courses",
        "Training",
        "tblRoleGroups",
        "tblPersonRoles",
        "tblCourseMatrix",
    }
    assert {"Params", "Overdue", "Next_Batch", "Individual_Lookup", "Course_Audit", "Sheet1"}.issubset(derived)
    assert WORKBOOK_SHEETS["Next_Batch"]["destination"] == "Smart scheduling and roster builder"
    assert WORKBOOK_SHEETS["Course_Audit"]["destination"] == "Training data rectification queue"


def test_people_sheet_preserves_multiple_amel_authorities_and_personnel_details():
    payload = _person_payload(
        {
            "PersonID": "eng01",
            "FIRSTNAME": "JANE",
            "LASTNAME": "DOE",
            "PersonName": "Jane Doe",
            "nid": "12345678",
            "Category (Reg. 2013)": "A&C",
            "Category (Reg. 2018)": "B1.1",
            "KAMEL NO:": "KCAA/AMEL/001",
            "E-AMEL": "ET-AMEL-22",
            "G-AMEL": "GH-AMEL-33",
            "Internal Certification Stamp No:": "STAMP-17",
            "initial_auth": date(2024, 2, 1),
            "Department": "Maintenance",
            "Position": "Certifying Engineer",
            "PhoneNumber": "0712345678",
            "Email": "JANE.DOE@EXAMPLE.COM",
            "HireDate": date(2020, 1, 10),
            "Employment_Status": "Permanent",
            "Status": "Active",
            "DOB": date(1990, 5, 2),
            "birthplace": "Nairobi",
        }
    )

    assert payload["person_id"] == "ENG01"
    assert payload["email"] == "jane.doe@example.com"
    assert payload["kamel_no"] == "KCAA/AMEL/001"
    assert payload["e_amel"] == "ET-AMEL-22"
    assert payload["g_amel"] == "GH-AMEL-33"
    assert payload["category_reg_2013"] == "A&C"
    assert payload["category_reg_2018"] == "B1.1"
    assert payload["internal_stamp_no"] == "STAMP-17"
    assert payload["initial_authorization_date"] == date(2024, 2, 1)


def test_courses_sheet_accepts_tracker_course_type_and_recurrent_frequency():
    payload = _course_payload(
        {
            "CourseID": "HF-REF",
            "CourseName": "Human Factors in Aviation (Refresher)",
            "FrequencyMonths": 24,
            "CourseType": "Recurrent",
            "Category": "Human Factors",
            "Mandatory": "Yes",
            "Scope": "ALL",
            "Reference": "KCAR Part 145",
        }
    )

    assert payload["course_id"] == "HF-REF"
    assert payload["status"] == "Recurrent"
    assert payload["frequency_months"] == 24
    assert payload["is_mandatory"] is True



def test_params_default_frequency_applies_to_recurrent_courses_without_override():
    params = _workbook_params([
        {"row_number": 2, "Setting": "Default Frequency (months)", "Value": 24},
    ])
    default_months = _default_frequency_months(params)
    payload = _course_payload(
        {
            "CourseID": "SMS-REF",
            "CourseName": "Safety Management Systems (Refresher)",
            "FrequencyMonths": None,
            "CourseType": "Recurrent",
            "Category": "SMS",
            "Mandatory": "Yes",
            "Scope": "ALL",
            "Reference": "KCAR",
        },
        default_frequency_months=default_months,
    )
    assert default_months == 24
    assert payload["frequency_months"] == 24
