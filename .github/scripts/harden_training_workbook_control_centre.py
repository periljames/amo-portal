from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Backend: workbook dependencies, Params policy, safe personnel identities.
# ---------------------------------------------------------------------------
path = "backend/amodb/apps/training/workbook_import.py"
text = read(path)
text = text.replace("import os\nimport re", "import os\nimport re\nimport secrets")

old_course_signature = "def _course_payload(raw: dict[str, Any]) -> dict[str, Any]:"
new_course_signature = "def _course_payload(raw: dict[str, Any], *, default_frequency_months: Optional[int] = None) -> dict[str, Any]:"
if old_course_signature in text:
    text = replace_once(text, old_course_signature, new_course_signature, "course payload signature")

old_frequency = '''    frequency = raw.get("FrequencyMonths")
    if frequency in (None, ""):
        months = None
    else:
        months = int(float(frequency))
        if months < 0:
            raise ValueError("FrequencyMonths cannot be negative")
'''
new_frequency = '''    frequency = raw.get("FrequencyMonths")
    if frequency in (None, ""):
        months = default_frequency_months if canonical == "Recurrent" else None
    else:
        months = int(float(frequency))
        if months < 0:
            raise ValueError("FrequencyMonths cannot be negative")
'''
if old_frequency in text:
    text = replace_once(text, old_frequency, new_frequency, "course default frequency")

params_anchor = "\ndef _role_from_position(position: Optional[str]) -> account_models.AccountRole:\n"
params_function = '''
def _workbook_params(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in rows:
        setting = clean(row.get("Setting"))
        if not setting:
            continue
        values[setting] = row.get("Value")
    return values


def _default_frequency_months(params: dict[str, Any]) -> Optional[int]:
    raw = params.get("Default Frequency (months)")
    if raw in (None, ""):
        return None
    value = int(float(raw))
    if value <= 0:
        raise ValueError("Default Frequency (months) must be a positive integer")
    return value


def _role_from_position(position: Optional[str]) -> account_models.AccountRole:
'''
if "def _workbook_params" not in text:
    text = replace_once(text, params_anchor, "\n" + params_function, "Params parser")

old_preview_courses_signature = "def _preview_courses(db: Session, job: TrainingWorkbookImportJob, sheet: TrainingWorkbookImportSheet, rows: list[dict[str, Any]]) -> None:"
new_preview_courses_signature = "def _preview_courses(db: Session, job: TrainingWorkbookImportJob, sheet: TrainingWorkbookImportSheet, rows: list[dict[str, Any]], *, default_frequency_months: Optional[int] = None) -> None:"
if old_preview_courses_signature in text:
    text = replace_once(text, old_preview_courses_signature, new_preview_courses_signature, "preview courses signature")
text = text.replace("payload = _course_payload(raw)\n", "payload = _course_payload(raw, default_frequency_months=default_frequency_months)\n", 1)

preview_training_pattern = re.compile(r"def _preview_training\(.*?\n\ndef _preview_role_groups", re.S)
preview_training_replacement = '''def _preview_training(
    db: Session,
    job: TrainingWorkbookImportJob,
    sheet: TrainingWorkbookImportSheet,
    rows: list[dict[str, Any]],
    *,
    workbook_people: set[str],
    workbook_courses: set[str],
) -> None:
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == job.amo_id,
        account_models.User.is_system_account.is_(False),
    ).all()
    courses = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == job.amo_id,
    ).all()
    by_staff, by_user_id, by_name = records_import._index_users(users)
    by_code, by_course_name = records_import._index_courses(courses)
    existing = {
        (str(item.user_id), str(item.course_id), item.completion_date): item
        for item in db.query(training_models.TrainingRecord)
        .filter(training_models.TrainingRecord.amo_id == job.amo_id)
        .all()
    }
    seen: set[tuple[str, str, date]] = set()
    for raw in rows:
        row_number = int(raw["row_number"])
        try:
            parsed = records_import._build_parsed_training_row(raw)
            source_key = f"{parsed.person_id}:{parsed.course_id}:{parsed.completion_date.isoformat()}"
            dedupe = (parsed.person_id, parsed.course_id, parsed.completion_date)
            if dedupe in seen:
                raise ValueError("Duplicate person/course/completion combination inside workbook")
            seen.add(dedupe)
            user = records_import._match_user(parsed, by_staff=by_staff, by_id=by_user_id, by_name=by_name)
            course = records_import._match_course(parsed, by_code=by_code, by_name=by_course_name)
            payload = {
                "RecordID": parsed.legacy_record_id,
                "PersonID": parsed.person_id,
                "PersonName": parsed.person_name,
                "CourseID": parsed.course_id,
                "CourseName": parsed.course_name,
                "LastTrainingDate": parsed.completion_date,
                "NextDueDate": parsed.next_due_date,
                "DaysToDue": parsed.days_to_due,
                "Status": parsed.source_status,
            }
            person_resolves_from_workbook = user is None and parsed.person_id in workbook_people
            course_resolves_from_workbook = course is None and parsed.course_id in workbook_courses
            if user is None and not person_resolves_from_workbook:
                item = _row(
                    job_id=job.id,
                    sheet="Training",
                    row_number=row_number,
                    entity_type="TRAINING_RECORD",
                    source_key=source_key,
                    label=f"{parsed.person_name or parsed.person_id} · {parsed.course_name}",
                    action="SKIP",
                    status="FAILED",
                    payload=payload,
                    issue_code="UNMATCHED_PERSON",
                    issue_message="PersonID is not present in the People sheet or the AMO personnel register.",
                )
                _counter(sheet, "SKIP", failed=True)
            elif course is None and not course_resolves_from_workbook:
                item = _row(
                    job_id=job.id,
                    sheet="Training",
                    row_number=row_number,
                    entity_type="TRAINING_RECORD",
                    source_key=source_key,
                    label=f"{parsed.person_name or parsed.person_id} · {parsed.course_name}",
                    action="SKIP",
                    status="FAILED",
                    payload=payload,
                    issue_code="UNMATCHED_COURSE",
                    issue_message="CourseID is not present in the Courses sheet or the AMO course catalogue.",
                )
                _counter(sheet, "SKIP", failed=True)
            elif person_resolves_from_workbook or course_resolves_from_workbook:
                dependencies = []
                if person_resolves_from_workbook:
                    dependencies.append("People")
                if course_resolves_from_workbook:
                    dependencies.append("Courses")
                item = _row(
                    job_id=job.id,
                    sheet="Training",
                    row_number=row_number,
                    entity_type="TRAINING_RECORD",
                    source_key=source_key,
                    label=f"{parsed.person_name or parsed.person_id} · {parsed.course_name}",
                    action="CREATE",
                    status="PENDING_DEPENDENCY",
                    payload=payload,
                    issue_code="WORKBOOK_DEPENDENCY",
                    issue_message=f"Will resolve after accepted {' and '.join(dependencies)} rows are committed.",
                )
                _counter(sheet, "CREATE")
            else:
                current = existing.get((str(user.id), str(course.id), parsed.completion_date))
                action = "CREATE" if current is None else "UPDATE"
                item = _row(
                    job_id=job.id,
                    sheet="Training",
                    row_number=row_number,
                    entity_type="TRAINING_RECORD",
                    source_key=source_key,
                    label=f"{getattr(user, 'full_name', parsed.person_id)} · {course.course_name}",
                    action=action,
                    payload=payload,
                )
                _counter(sheet, action)
            db.add(item)
        except Exception as exc:
            db.add(_row(
                job_id=job.id,
                sheet="Training",
                row_number=row_number,
                entity_type="TRAINING_RECORD",
                source_key=None,
                label=f"{clean(raw.get('PersonName')) or clean(raw.get('PersonID')) or 'Training row'} · {clean(raw.get('CourseName')) or clean(raw.get('CourseID')) or ''}",
                action="SKIP",
                status="FAILED",
                payload=raw,
                issue_code="INVALID_TRAINING_RECORD",
                issue_message=str(exc),
            ))
            _counter(sheet, "SKIP", failed=True)
        _set_job_progress(
            db,
            job,
            stage="MATCHING",
            sheet="Training",
            label=f"{clean(raw.get('PersonName')) or clean(raw.get('PersonID')) or 'Training row'} · {clean(raw.get('CourseID')) or ''}",
            processed_delta=1,
        )


def _preview_role_groups'''
if preview_training_pattern.search(text):
    text = preview_training_pattern.sub(preview_training_replacement, text, count=1)
else:
    raise RuntimeError("Could not locate training preview function")

old_process_setup = '''        course_rows = rows_by_sheet.get("Courses", [])
        people_rows = [item for item in rows_by_sheet.get("People", []) if upper(item.get("PersonID")) != "TOTAL"]
        known_courses = {upper(item.get("CourseID")) for item in course_rows if upper(item.get("CourseID"))}
'''
new_process_setup = '''        params = _workbook_params(rows_by_sheet.get("Params", []))
        default_frequency_months = _default_frequency_months(params)
        job.summary_json = {
            **(job.summary_json or {}),
            "policy_defaults": {
                "default_frequency_months": default_frequency_months,
            },
        }
        db.add(job)
        db.commit()

        course_rows = rows_by_sheet.get("Courses", [])
        people_rows = [item for item in rows_by_sheet.get("People", []) if upper(item.get("PersonID")) != "TOTAL"]
        workbook_courses = {upper(item.get("CourseID")) for item in course_rows if upper(item.get("CourseID"))}
        workbook_people = {upper(item.get("PersonID")) for item in people_rows if upper(item.get("PersonID"))}
        known_courses = set(workbook_courses)
'''
if old_process_setup in text:
    text = replace_once(text, old_process_setup, new_process_setup, "process workbook Params setup")
text = text.replace('        known_people = {upper(item.get("PersonID")) for item in people_rows if upper(item.get("PersonID"))}\n', '        known_people = set(workbook_people)\n')
text = text.replace('processors.append(("Courses", lambda: _preview_courses(db, job, sheets["Courses"], course_rows)))', 'processors.append(("Courses", lambda: _preview_courses(db, job, sheets["Courses"], course_rows, default_frequency_months=default_frequency_months)))')
text = text.replace('processors.append(("Training", lambda: _preview_training(db, job, sheets["Training"], rows_by_sheet.get("Training", []))))', 'processors.append(("Training", lambda: _preview_training(db, job, sheets["Training"], rows_by_sheet.get("Training", []), workbook_people=workbook_people, workbook_courses=workbook_courses)))')

old_account_block_pattern = re.compile(
    r'''    create_account = decision == "CREATE_ACCOUNT"\n    profile_only = decision == "PROFILE_ONLY" or \(is_new and not create_account\)\n    if user is None and create_account:.*?    elif user is not None:\n''',
    re.S,
)
new_account_block = '''    create_account = decision == "CREATE_ACCOUNT"
    personnel_only = decision == "PROFILE_ONLY" or (is_new and not create_account)
    if user is None and (create_account or personnel_only):
        if create_account and not selected_email:
            raise ValueError("A portal-access candidate requires a valid email address")
        identity_email = selected_email or f"{person_id.lower()}@personnel.invalid"
        approval_note = (
            "Imported from Training Tracker; pending administrator approval and onboarding."
            if create_account
            else "Personnel-only identity imported for training and licence records; portal access disabled."
        )
        user = account_models.User(
            id=generate_user_id(),
            amo_id=job.amo_id,
            department_id=_department_id(db, job.amo_id, payload.get("department")),
            staff_code=person_id,
            email=identity_email,
            first_name=payload["first_name"],
            last_name=payload["last_name"],
            full_name=payload.get("full_name") or f"{payload['first_name']} {payload['last_name']}",
            role=_role_from_position(payload.get("position_title")),
            position_title=payload.get("position_title"),
            phone=payload.get("phone_number"),
            secondary_phone=payload.get("secondary_phone"),
            hashed_password=get_password_hash(secrets.token_urlsafe(48)),
            is_active=False,
            is_amo_admin=False,
            is_auditor=False,
            must_change_password=True,
            approved_by_user_id=None,
            approved_at=None,
            approval_notes=approval_note,
        )
        db.add(user)
        db.flush()
        profile.user_id = user.id
    elif user is not None:
'''
if old_account_block_pattern.search(text):
    text = old_account_block_pattern.sub(new_account_block, text, count=1)
else:
    raise RuntimeError("Could not locate account creation block")

text = text.replace(
    '        user.is_active = str(payload.get("status") or "Active").lower() == "active"\n',
    '        if str(payload.get("status") or "Active").lower() != "active":\n            user.is_active = False\n',
    1,
)
write(path, text)


# ---------------------------------------------------------------------------
# Backend: guard matrix reads during rolling deployments and clean router.
# ---------------------------------------------------------------------------
path = "backend/amodb/apps/training/compliance.py"
text = read(path)
text = text.replace("from sqlalchemy import or_", "from sqlalchemy import inspect, or_")
role_pattern = re.compile(
    r'''    # Role groups and matrix rules imported from the governed Training Tracker.*?\n    return sorted\(set\(required_course_ids\)\)''',
    re.S,
)
role_replacement = '''    # Role groups and matrix rules imported from the governed Training Tracker
    # extend the canonical requirement model. Guard the optional tables so a
    # rolling deployment cannot interrupt existing compliance reads before the
    # Alembic migration reaches every application instance.
    inspector = inspect(db.get_bind())
    if inspector.has_table("training_role_groups") and inspector.has_table("training_course_role_rules"):
        role_group_ids = [
            group_id
            for (group_id,) in db.query(training_workbook_models.TrainingRoleGroup.id)
            .filter(
                training_workbook_models.TrainingRoleGroup.amo_id == user.amo_id,
                training_workbook_models.TrainingRoleGroup.is_active.is_(True),
                training_workbook_models.TrainingRoleGroup.code == "ALL",
            )
            .all()
        ]
        assignment_query = db.query(training_workbook_models.TrainingPersonRole.role_group_id).filter(
            training_workbook_models.TrainingPersonRole.amo_id == user.amo_id,
            training_workbook_models.TrainingPersonRole.is_active.is_(True),
        )
        person_terms = [training_workbook_models.TrainingPersonRole.user_id == user.id]
        if getattr(user, "staff_code", None):
            person_terms.append(training_workbook_models.TrainingPersonRole.person_id == str(user.staff_code).strip().upper())
        assignment_query = assignment_query.filter(or_(*person_terms))
        role_group_ids.extend(group_id for (group_id,) in assignment_query.all())
        if role_group_ids:
            required_course_ids.extend(
                course_id
                for (course_id,) in db.query(training_workbook_models.TrainingCourseRoleRule.course_id)
                .filter(
                    training_workbook_models.TrainingCourseRoleRule.amo_id == user.amo_id,
                    training_workbook_models.TrainingCourseRoleRule.role_group_id.in_(sorted(set(role_group_ids))),
                    training_workbook_models.TrainingCourseRoleRule.is_active.is_(True),
                    training_workbook_models.TrainingCourseRoleRule.is_required.is_(True),
                )
                .all()
            )

    return sorted(set(required_course_ids))'''
if role_pattern.search(text):
    text = role_pattern.sub(role_replacement, text, count=1)
else:
    raise RuntimeError("Could not locate imported role matrix logic")
write(path, text)

path = "backend/amodb/apps/training/workbook_router.py"
text = read(path)
if "from . import models as training_models" not in text:
    text = replace_once(text, "from . import compliance as training_compliance\n", "from . import compliance as training_compliance\nfrom . import models as training_models\n", "workbook router models import")
old_query = '''    rows = db.query(TrainingCourseRoleRule, TrainingRoleGroup, __import__("amodb.apps.training.models", fromlist=["TrainingCourse"]).TrainingCourse).join(TrainingRoleGroup, TrainingCourseRoleRule.role_group_id == TrainingRoleGroup.id).join(__import__("amodb.apps.training.models", fromlist=["TrainingCourse"]).TrainingCourse, TrainingCourseRoleRule.course_id == __import__("amodb.apps.training.models", fromlist=["TrainingCourse"]).TrainingCourse.id).filter(TrainingCourseRoleRule.amo_id == current_user.amo_id, TrainingCourseRoleRule.is_active.is_(True)).all()
'''
new_query = '''    rows = (
        db.query(TrainingCourseRoleRule, TrainingRoleGroup, training_models.TrainingCourse)
        .join(TrainingRoleGroup, TrainingCourseRoleRule.role_group_id == TrainingRoleGroup.id)
        .join(training_models.TrainingCourse, TrainingCourseRoleRule.course_id == training_models.TrainingCourse.id)
        .filter(
            TrainingCourseRoleRule.amo_id == current_user.amo_id,
            TrainingCourseRoleRule.is_active.is_(True),
        )
        .order_by(TrainingRoleGroup.code.asc(), training_models.TrainingCourse.course_id.asc())
        .all()
    )
'''
if old_query in text:
    text = replace_once(text, old_query, new_query, "role rules query")
write(path, text)


# ---------------------------------------------------------------------------
# Frontend wording: accounts are reviewed, not silently activated.
# ---------------------------------------------------------------------------
path = "frontend/src/components/training/TrainingWorkbookImportDialog.tsx"
text = read(path)
text = text.replace(
    'CREATE_ACCOUNT: "Create personnel profile and portal account",',
    'CREATE_ACCOUNT: "Create inactive account for approval and onboarding",',
)
text = text.replace(
    'New people are never silently given portal access. Accept each as a user, personnel-only record, or skip it.',
    'New people are never silently activated. Create an inactive account for approval, keep a non-login personnel identity, or skip the row.',
)
write(path, text)


# ---------------------------------------------------------------------------
# Tests: Params policy and same-workbook dependencies.
# ---------------------------------------------------------------------------
path = "backend/amodb/apps/training/tests/test_workbook_import_mapping.py"
text = read(path)
text = text.replace(
    "from amodb.apps.training.workbook_import import WORKBOOK_SHEETS, _course_payload, _person_payload",
    "from amodb.apps.training.workbook_import import WORKBOOK_SHEETS, _course_payload, _default_frequency_months, _person_payload, _workbook_params",
)
append = '''


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
'''
if "test_params_default_frequency_applies" not in text:
    text += append
write(path, text)


# Syntax checks before the frontend build in the workflow.
subprocess.run(
    [
        "python",
        "-m",
        "py_compile",
        "backend/amodb/apps/training/workbook_import.py",
        "backend/amodb/apps/training/workbook_router.py",
        "backend/amodb/apps/training/compliance.py",
        "backend/amodb/apps/training/records_import.py",
        "backend/amodb/apps/training/workbook_models.py",
        "backend/amodb/apps/training/workbook_schemas.py",
        "backend/amodb/apps/training/tests/test_workbook_import_mapping.py",
    ],
    cwd=ROOT,
    check=True,
)
