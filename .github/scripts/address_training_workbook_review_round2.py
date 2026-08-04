from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Backend importer hardening.
# ---------------------------------------------------------------------------
path = "backend/amodb/apps/training/workbook_import.py"
text = read(path)
if "from sqlalchemy.exc import IntegrityError" not in text:
    text = replace_once(
        text,
        "from sqlalchemy import func\nfrom sqlalchemy.orm import Session\n",
        "from sqlalchemy import func\nfrom sqlalchemy.exc import IntegrityError\nfrom sqlalchemy.orm import Session\n",
        "IntegrityError import",
    )

utc_anchor = '''def utcnow() -> datetime:
    return datetime.now(timezone.utc)


'''
review_exception = '''def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportReviewRequired(RuntimeError):
    """Abort the operational transaction and return the job to row review."""

    def __init__(
        self,
        *,
        row_id: str,
        message: str,
        decision_options: list[str],
        issue_code: str = "IDENTITY_CHANGED",
    ) -> None:
        super().__init__(message)
        self.row_id = row_id
        self.message = message
        self.decision_options = decision_options
        self.issue_code = issue_code


def _identity_change_options(*, has_same_person_account: bool, has_conflicting_email_owner: bool) -> list[str]:
    if has_same_person_account:
        return ["LINK_EXISTING_ACCOUNT", "KEEP_EXISTING_EMAIL", "SKIP"]
    if has_conflicting_email_owner:
        return ["SKIP"]
    return ["SKIP"]


def _retired_licence_status(incoming_number: Optional[str]) -> str:
    return "SUPERSEDED" if clean(incoming_number) else "RETIRED"


def _should_materialize_catalogue_fallback(*, has_active_requirements: bool, has_required_all_rule: bool) -> bool:
    return has_required_all_rule and not has_active_requirements


'''
if "class ImportReviewRequired" not in text:
    text = replace_once(text, utc_anchor, review_exception, "review exception and pure helpers")

licence_pattern = re.compile(r"def _upsert_licence\(.*?\n\ndef _upsert_person", re.S)
licence_replacement = '''def _upsert_licence(
    db: Session,
    *,
    job: TrainingWorkbookImportJob,
    profile: account_models.PersonnelProfile,
    user: Optional[account_models.User],
    authority: str,
    country: str,
    number: Optional[str],
    category: Optional[str],
    category_source: Optional[str],
    payload: dict[str, Any],
    source_row: int,
    primary: bool,
) -> None:
    incoming_number = clean(number)
    existing = db.query(PersonnelLicence).filter(
        PersonnelLicence.amo_id == job.amo_id,
        PersonnelLicence.personnel_profile_id == profile.id,
        PersonnelLicence.authority == authority,
    ).all()
    matching = next((item for item in existing if clean(item.licence_number) == incoming_number), None) if incoming_number else None

    # The People sheet is the current authority register. Retain superseded
    # credentials for audit history, but never leave a replaced/cleared number
    # active or primary.
    replacement_status = _retired_licence_status(incoming_number)
    for credential in existing:
        if matching is not None and credential.id == matching.id:
            continue
        if credential.status not in {"SUPERSEDED", "RETIRED"} or credential.is_primary:
            credential.status = replacement_status
            credential.is_primary = False
            credential.source_job_id = job.id
            credential.source_row = source_row
            credential.updated_at = utcnow()
            db.add(credential)

    if not incoming_number:
        return

    licence = matching
    if licence is None:
        licence = PersonnelLicence(
            amo_id=job.amo_id,
            personnel_profile_id=profile.id,
            authority=authority,
            licence_number=incoming_number,
        )
        db.add(licence)
    licence.user_id = user.id if user else None
    licence.country = country
    licence.category_code = category
    licence.category_source = category_source
    licence.internal_stamp_no = payload.get("internal_stamp_no")
    licence.initial_authorization_date = date_value(payload.get("initial_authorization_date"))
    licence.status = "ACTIVE" if str(payload.get("status") or "Active").lower() == "active" else "DORMANT"
    licence.is_primary = primary
    licence.source_job_id = job.id
    licence.source_row = source_row
    licence.updated_at = utcnow()


def _existing_person_accounts(
    db: Session,
    *,
    amo_id: str,
    person_id: str,
    email: Optional[str],
    profile: Optional[account_models.PersonnelProfile] = None,
) -> tuple[Optional[account_models.User], Optional[account_models.User], Optional[account_models.User]]:
    profile_user = db.get(account_models.User, profile.user_id) if profile and profile.user_id else None
    staff_user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.staff_code == person_id,
    ).first()
    email_user = None
    if email:
        email_user = db.query(account_models.User).filter(
            account_models.User.amo_id == amo_id,
            func.lower(account_models.User.email) == str(email).lower(),
        ).first()
    return profile_user, staff_user, email_user


def _raise_identity_review(
    *,
    row: TrainingWorkbookImportRow,
    person_id: str,
    profile_user: Optional[account_models.User],
    staff_user: Optional[account_models.User],
    email_user: Optional[account_models.User],
    message: str,
) -> None:
    same_person_email_user = bool(email_user and upper(email_user.staff_code) == person_id)
    same_person = bool(profile_user or staff_user or same_person_email_user)
    conflicting_email = bool(email_user and not same_person_email_user)
    raise ImportReviewRequired(
        row_id=row.id,
        message=message,
        decision_options=_identity_change_options(
            has_same_person_account=same_person,
            has_conflicting_email_owner=conflicting_email,
        ),
    )


def _upsert_person'''
if not licence_pattern.search(text):
    raise RuntimeError("Could not locate licence/person functions")
text = licence_pattern.sub(licence_replacement, text, count=1)

person_pattern = re.compile(r"def _upsert_person\(.*?\n\ndef _progress_callback", re.S)
person_replacement = '''def _upsert_person(db: Session, job: TrainingWorkbookImportJob, row: TrainingWorkbookImportRow) -> tuple[Optional[str], str]:
    payload = dict(row.payload_json or {})
    person_id = upper(payload.get("person_id"))
    decision = (row.decision or "").upper()
    if decision == "SKIP":
        return None, "SKIP"

    profile_by_person = db.query(account_models.PersonnelProfile).filter(
        account_models.PersonnelProfile.amo_id == job.amo_id,
        account_models.PersonnelProfile.person_id == person_id,
    ).first()
    profile_by_email = None
    if payload.get("email"):
        profile_by_email = db.query(account_models.PersonnelProfile).filter(
            account_models.PersonnelProfile.amo_id == job.amo_id,
            func.lower(account_models.PersonnelProfile.email) == str(payload["email"]).lower(),
        ).first()
    if profile_by_email and upper(profile_by_email.person_id) != person_id:
        profile_by_email = None
    profile = profile_by_person or profile_by_email
    is_new = profile is None
    if profile is None:
        profile = account_models.PersonnelProfile(
            amo_id=job.amo_id,
            person_id=person_id,
            first_name=payload["first_name"],
            last_name=payload["last_name"],
        )
        db.add(profile)
        db.flush()

    profile_user, staff_user, email_user = _existing_person_accounts(
        db,
        amo_id=job.amo_id,
        person_id=person_id,
        email=payload.get("email"),
        profile=profile,
    )
    same_person_email_user = email_user if email_user and upper(email_user.staff_code) == person_id else None
    safe_existing_user = profile_user or staff_user or same_person_email_user

    # CREATE_ACCOUNT and PROFILE_ONLY are approvals of a specific access state.
    # Any account discovered at commit time is a changed identity condition and
    # must return to review rather than silently becoming a link/update action.
    if decision in {"CREATE_ACCOUNT", "PROFILE_ONLY"} and (profile_user or staff_user or email_user):
        _raise_identity_review(
            row=row,
            person_id=person_id,
            profile_user=profile_user,
            staff_user=staff_user,
            email_user=email_user,
            message="A portal account appeared after preview. Review the changed identity before continuing.",
        )

    imported_email = payload.get("email")
    if decision == "KEEP_EXISTING_EMAIL":
        selected_email = (profile_by_person.email if profile_by_person else None) or (safe_existing_user.email if safe_existing_user else None)
        if not selected_email:
            raise ImportReviewRequired(
                row_id=row.id,
                message="No same-person existing email remains available. Review this personnel identity again.",
                decision_options=["SKIP"],
            )
    else:
        selected_email = imported_email or profile.email

    profile.person_id = person_id
    profile.first_name = payload["first_name"]
    profile.last_name = payload["last_name"]
    profile.full_name = payload.get("full_name")
    profile.national_id = payload.get("national_id")
    profile.amel_no = payload.get("kamel_no")
    profile.internal_certification_stamp_no = payload.get("internal_stamp_no")
    profile.initial_authorization_date = date_value(payload.get("initial_authorization_date"))
    profile.department = payload.get("department")
    profile.position_title = payload.get("position_title")
    profile.phone_number = payload.get("phone_number")
    profile.secondary_phone = payload.get("secondary_phone")
    profile.email = selected_email
    profile.hire_date = date_value(payload.get("hire_date"))
    profile.employment_status = payload.get("employment_status")
    profile.status = payload.get("status") or "Active"
    profile.date_of_birth = date_value(payload.get("date_of_birth"))
    profile.birth_place = payload.get("birth_place")
    db.flush()

    user: Optional[account_models.User]
    if decision == "PROFILE_ONLY":
        user = account_models.User(
            id=generate_user_id(),
            amo_id=job.amo_id,
            department_id=_department_id(db, job.amo_id, payload.get("department")),
            staff_code=person_id,
            email=f"{person_id.lower()}@personnel.invalid",
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
            approval_notes="Personnel-only identity imported for licence and training history; portal access disabled.",
        )
        try:
            with db.begin_nested():
                db.add(user)
                db.flush()
        except IntegrityError as exc:
            profile_user, staff_user, email_user = _existing_person_accounts(
                db,
                amo_id=job.amo_id,
                person_id=person_id,
                email=payload.get("email"),
                profile=profile,
            )
            _raise_identity_review(
                row=row,
                person_id=person_id,
                profile_user=profile_user,
                staff_user=staff_user,
                email_user=email_user,
                message="The personnel-only identity collided with an account created concurrently. Review the identity again.",
            )
            raise exc  # pragma: no cover
        profile.user_id = user.id
    elif decision == "CREATE_ACCOUNT":
        if not selected_email:
            raise ValueError("A portal-access candidate requires a valid email address")
        user = account_models.User(
            id=generate_user_id(),
            amo_id=job.amo_id,
            department_id=_department_id(db, job.amo_id, payload.get("department")),
            staff_code=person_id,
            email=selected_email,
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
            approval_notes="Imported from Training Tracker; pending administrator approval and onboarding.",
        )
        try:
            with db.begin_nested():
                db.add(user)
                db.flush()
        except IntegrityError as exc:
            profile_user, staff_user, email_user = _existing_person_accounts(
                db,
                amo_id=job.amo_id,
                person_id=person_id,
                email=selected_email,
                profile=profile,
            )
            _raise_identity_review(
                row=row,
                person_id=person_id,
                profile_user=profile_user,
                staff_user=staff_user,
                email_user=email_user,
                message="An account was created concurrently after approval. Review whether it should be linked or skipped.",
            )
            raise exc  # pragma: no cover
        profile.user_id = user.id
    else:
        user = safe_existing_user
        if decision == "LINK_EXISTING_ACCOUNT" and user is None:
            raise ImportReviewRequired(
                row_id=row.id,
                message="The same-person account selected for linking no longer exists. Review the row again.",
                decision_options=["SKIP"],
            )
        if user is not None:
            user.department_id = _department_id(db, job.amo_id, payload.get("department")) or user.department_id
            user.first_name = payload["first_name"]
            user.last_name = payload["last_name"]
            user.full_name = payload.get("full_name") or user.full_name
            user.position_title = payload.get("position_title")
            user.phone = payload.get("phone_number")
            user.secondary_phone = payload.get("secondary_phone")
            if str(payload.get("status") or "Active").lower() != "active":
                user.is_active = False
            if selected_email and decision != "KEEP_EXISTING_EMAIL":
                user.email = selected_email
            profile.user_id = user.id

    kamel_number = clean(payload.get("kamel_no"))
    if user:
        if kamel_number:
            user.regulatory_authority = account_models.RegulatoryAuthority.KCAA
            user.licence_number = kamel_number
            user.licence_state_or_country = "Kenya"
        elif user.regulatory_authority == account_models.RegulatoryAuthority.KCAA:
            user.regulatory_authority = None
            user.licence_number = None
            user.licence_state_or_country = None
            user.licence_expires_on = None

    category = payload.get("category_reg_2018") or payload.get("category_reg_2013")
    category_source = "Reg. 2018" if payload.get("category_reg_2018") else "Reg. 2013" if payload.get("category_reg_2013") else None
    _upsert_licence(db, job=job, profile=profile, user=user, authority="KCAA", country="Kenya", number=kamel_number, category=category, category_source=category_source, payload=payload, source_row=row.source_row, primary=True)
    _upsert_licence(db, job=job, profile=profile, user=user, authority="ETHIOPIAN_CAA", country="Ethiopia", number=payload.get("e_amel"), category=None, category_source=None, payload=payload, source_row=row.source_row, primary=False)
    _upsert_licence(db, job=job, profile=profile, user=user, authority="GHANA_CAA", country="Ghana", number=payload.get("g_amel"), category=None, category_source=None, payload=payload, source_row=row.source_row, primary=False)
    db.flush()
    return str(user.id if user else profile.id), "CREATE" if is_new else "UPDATE"


def _revalidate_people_access_decisions(
    db: Session,
    *,
    job: TrainingWorkbookImportJob,
    rows: list[TrainingWorkbookImportRow],
) -> bool:
    changed_rows: list[TrainingWorkbookImportRow] = []
    for row in rows:
        if row.sheet_name != "People" or row.status == "FAILED":
            continue
        decision = (row.decision or "").upper()
        if decision not in {"CREATE_ACCOUNT", "PROFILE_ONLY"}:
            continue
        payload = dict(row.payload_json or {})
        person_id = upper(payload.get("person_id"))
        profile = db.query(account_models.PersonnelProfile).filter(
            account_models.PersonnelProfile.amo_id == job.amo_id,
            account_models.PersonnelProfile.person_id == person_id,
        ).first()
        profile_user, staff_user, email_user = _existing_person_accounts(
            db,
            amo_id=job.amo_id,
            person_id=person_id,
            email=payload.get("email"),
            profile=profile,
        )
        if not (profile_user or staff_user or email_user):
            continue
        same_person_email_user = bool(email_user and upper(email_user.staff_code) == person_id)
        row.status = "REVIEW"
        row.decision = None
        row.decision_required = True
        row.decision_options = _identity_change_options(
            has_same_person_account=bool(profile_user or staff_user or same_person_email_user),
            has_conflicting_email_owner=bool(email_user and not same_person_email_user),
        )
        row.issue_code = "IDENTITY_CHANGED"
        row.issue_message = "A portal account appeared after preview. Review the changed identity before committing."
        row.updated_at = utcnow()
        db.add(row)
        changed_rows.append(row)

    if not changed_rows:
        return True

    job.status = "REVIEW_REQUIRED"
    job.stage = "REVIEW"
    job.current_sheet = "People"
    job.current_record_label = changed_rows[0].display_label
    job.error_message = f"{len(changed_rows)} personnel identity decision(s) changed after preview and require review."
    job.completed_at = utcnow()
    db.flush()
    job.review_count = db.query(TrainingWorkbookImportRow).filter(
        TrainingWorkbookImportRow.job_id == job.id,
        TrainingWorkbookImportRow.decision_required.is_(True),
        TrainingWorkbookImportRow.decision.is_(None),
    ).count()
    db.add(job)
    db.commit()
    return False


def _materialize_catalogue_fallback_requirements(
    db: Session,
    *,
    job: TrainingWorkbookImportJob,
    matrix_rows: list[TrainingWorkbookImportRow],
) -> None:
    has_required_all_rule = any(
        row.status != "FAILED"
        and upper((row.payload_json or {}).get("role_group")) == "ALL"
        and bool((row.payload_json or {}).get("is_required", True))
        for row in matrix_rows
    )
    has_active_requirements = db.query(training_models.TrainingRequirement.id).filter(
        training_models.TrainingRequirement.amo_id == job.amo_id,
        training_models.TrainingRequirement.is_active.is_(True),
        training_models.TrainingRequirement.is_mandatory.is_(True),
    ).first() is not None
    if not _should_materialize_catalogue_fallback(
        has_active_requirements=has_active_requirements,
        has_required_all_rule=has_required_all_rule,
    ):
        return

    mandatory_courses = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == job.amo_id,
        training_models.TrainingCourse.is_active.is_(True),
        training_models.TrainingCourse.is_mandatory.is_(True),
    ).all()
    for course in mandatory_courses:
        canonical = db.query(training_models.TrainingRequirement).filter(
            training_models.TrainingRequirement.amo_id == job.amo_id,
            training_models.TrainingRequirement.course_id == course.id,
            training_models.TrainingRequirement.scope == training_models.TrainingRequirementScope.ALL,
        ).first()
        if canonical is not None:
            continue
        db.add(training_models.TrainingRequirement(
            amo_id=job.amo_id,
            course_id=course.id,
            scope=training_models.TrainingRequirementScope.ALL,
            is_mandatory=True,
            is_active=True,
            created_by_user_id=job.actor_user_id,
        ))
    db.flush()


def _progress_callback'''
if not person_pattern.search(text):
    raise RuntimeError("Could not locate personnel function")
text = person_pattern.sub(person_replacement, text, count=1)

commit_pattern = re.compile(r"def commit_workbook_import\(.*\Z", re.S)
commit_replacement = '''def commit_workbook_import(job_id: str, *, force_reimport: bool = False) -> None:
    progress_db = SessionLocal()
    work_db = SessionLocal()
    try:
        job = progress_db.get(TrainingWorkbookImportJob, job_id)
        if not job:
            return
        duplicate = progress_db.query(TrainingWorkbookImportJob).filter(
            TrainingWorkbookImportJob.amo_id == job.amo_id,
            TrainingWorkbookImportJob.file_sha256 == job.file_sha256,
            TrainingWorkbookImportJob.status == "COMPLETED",
            TrainingWorkbookImportJob.committed_at.isnot(None),
            TrainingWorkbookImportJob.id != job.id,
        ).order_by(TrainingWorkbookImportJob.committed_at.desc()).first()
        if duplicate and not force_reimport:
            raise ValueError(f"This workbook was already committed by import {duplicate.id}. Use force re-import only after reviewing the reconciliation.")

        unresolved = progress_db.query(TrainingWorkbookImportRow).filter(
            TrainingWorkbookImportRow.job_id == job.id,
            TrainingWorkbookImportRow.decision_required.is_(True),
            TrainingWorkbookImportRow.decision.is_(None),
        ).count()
        if unresolved:
            raise ValueError(f"{unresolved} review decision(s) are still required before commit.")

        rows = progress_db.query(TrainingWorkbookImportRow).filter(
            TrainingWorkbookImportRow.job_id == job.id,
        ).order_by(
            TrainingWorkbookImportRow.sheet_name,
            TrainingWorkbookImportRow.source_row,
        ).all()
        if not _revalidate_people_access_decisions(progress_db, job=job, rows=rows):
            return

        job.status = "COMMITTING"
        job.stage = "COMMITTING_COURSES"
        job.processed_rows = 0
        job.current_sheet = "Courses"
        job.current_record_label = None
        job.error_message = None
        progress_db.add(job)
        progress_db.commit()

        # Detach all row-result objects before progress publication. Progress
        # commits must never flush committed_entity_id/status markers until the
        # separate operational transaction has succeeded.
        progress_db.expunge_all()
        rows_by_sheet: dict[str, list[TrainingWorkbookImportRow]] = {}
        for item in rows:
            rows_by_sheet.setdefault(item.sheet_name, []).append(item)

        total_processed = 0
        with work_db.begin():
            course_rows = rows_by_sheet.get("Courses", [])
            if course_rows:
                _commit_progress(job.id, total_processed, "COMMITTING_COURSES", "Courses", None)
            for index, item in enumerate(course_rows, start=1):
                if item.status != "FAILED" and item.proposed_action != "SKIP":
                    entity = _upsert_course(work_db, job.amo_id, dict(item.payload_json or {}), job.actor_user_id)
                    item.committed_entity_id = entity.id
                total_processed += 1
                if index % 10 == 0 or index == len(course_rows):
                    _commit_progress(job.id, total_processed, "COMMITTING_COURSES", "Courses", item.display_label)

            people_rows = rows_by_sheet.get("People", [])
            if people_rows:
                _commit_progress(job.id, total_processed, "COMMITTING_PEOPLE", "People", None)
            for index, item in enumerate(people_rows, start=1):
                if item.status != "FAILED":
                    try:
                        entity_id, action = _upsert_person(work_db, job, item)
                        item.committed_entity_id = entity_id
                        if action == "SKIP":
                            item.status = "SKIPPED"
                    except ImportReviewRequired:
                        raise
                    except Exception as exc:
                        item.status = "FAILED"
                        item.issue_code = "PERSON_COMMIT_FAILED"
                        item.issue_message = str(exc)
                total_processed += 1
                if index % 5 == 0 or index == len(people_rows):
                    _commit_progress(job.id, total_processed, "COMMITTING_PEOPLE", "People", item.display_label)

            role_group_rows = rows_by_sheet.get("tblRoleGroups", [])
            groups: dict[str, TrainingRoleGroup] = {}
            if role_group_rows:
                _commit_progress(job.id, total_processed, "COMMITTING_ROLE_GROUPS", "tblRoleGroups", None)
            for index, item in enumerate(role_group_rows, start=1):
                if item.status != "FAILED":
                    payload = dict(item.payload_json or {})
                    code = upper(payload.get("code"))
                    group = work_db.query(TrainingRoleGroup).filter(
                        TrainingRoleGroup.amo_id == job.amo_id,
                        TrainingRoleGroup.code == code,
                    ).first()
                    if group is None:
                        group = TrainingRoleGroup(amo_id=job.amo_id, code=code)
                        work_db.add(group)
                    group.description = payload.get("description")
                    group.is_active = True
                    group.source_job_id = job.id
                    work_db.flush()
                    groups[code] = group
                    item.committed_entity_id = group.id
                total_processed += 1
                if index % 10 == 0 or index == len(role_group_rows):
                    _commit_progress(job.id, total_processed, "COMMITTING_ROLE_GROUPS", "tblRoleGroups", item.display_label)

            profiles = {
                upper(profile.person_id): profile
                for profile in work_db.query(account_models.PersonnelProfile).filter(
                    account_models.PersonnelProfile.amo_id == job.amo_id,
                ).all()
            }
            users = {
                upper(user.staff_code): user
                for user in work_db.query(account_models.User).filter(
                    account_models.User.amo_id == job.amo_id,
                ).all()
            }
            groups.update({
                upper(group.code): group
                for group in work_db.query(TrainingRoleGroup).filter(
                    TrainingRoleGroup.amo_id == job.amo_id,
                ).all()
            })

            person_role_rows = rows_by_sheet.get("tblPersonRoles", [])
            if person_role_rows:
                _commit_progress(job.id, total_processed, "COMMITTING_PERSON_ROLES", "tblPersonRoles", None)
            for index, item in enumerate(person_role_rows, start=1):
                if item.status != "FAILED":
                    payload = dict(item.payload_json or {})
                    profile = profiles.get(upper(payload.get("person_id")))
                    group = groups.get(upper(payload.get("role_group")))
                    if not profile or not group:
                        item.status = "FAILED"
                        item.issue_message = "Person or role group was not available at commit."
                    else:
                        assignment = work_db.query(TrainingPersonRole).filter(
                            TrainingPersonRole.amo_id == job.amo_id,
                            TrainingPersonRole.person_id == profile.person_id,
                            TrainingPersonRole.role_group_id == group.id,
                        ).first()
                        if assignment is None:
                            assignment = TrainingPersonRole(
                                amo_id=job.amo_id,
                                person_id=profile.person_id,
                                role_group_id=group.id,
                            )
                            work_db.add(assignment)
                        assignment.personnel_profile_id = profile.id
                        assignment.user_id = users.get(upper(profile.person_id)).id if users.get(upper(profile.person_id)) else profile.user_id
                        assignment.department = payload.get("department")
                        assignment.position = payload.get("position")
                        assignment.notes = payload.get("notes")
                        assignment.is_active = bool(payload.get("is_active", True))
                        assignment.source_job_id = job.id
                        work_db.flush()
                        item.committed_entity_id = assignment.id
                total_processed += 1
                if index % 10 == 0 or index == len(person_role_rows):
                    _commit_progress(job.id, total_processed, "COMMITTING_PERSON_ROLES", "tblPersonRoles", item.display_label)

            courses = {
                upper(course.course_id): course
                for course in work_db.query(training_models.TrainingCourse).filter(
                    training_models.TrainingCourse.amo_id == job.amo_id,
                ).all()
            }
            matrix_rows = rows_by_sheet.get("tblCourseMatrix", [])
            _materialize_catalogue_fallback_requirements(work_db, job=job, matrix_rows=matrix_rows)
            if matrix_rows:
                _commit_progress(job.id, total_processed, "COMMITTING_COURSE_MATRIX", "tblCourseMatrix", None)
            for index, item in enumerate(matrix_rows, start=1):
                if item.status != "FAILED":
                    payload = dict(item.payload_json or {})
                    course = courses.get(upper(payload.get("course_id")))
                    group = groups.get(upper(payload.get("role_group")))
                    if not course or not group:
                        item.status = "FAILED"
                        item.issue_message = "Course or role group was not available at commit."
                    else:
                        requirement_type = payload.get("requirement_type") or "GENERAL"
                        rule = work_db.query(TrainingCourseRoleRule).filter(
                            TrainingCourseRoleRule.amo_id == job.amo_id,
                            TrainingCourseRoleRule.course_id == course.id,
                            TrainingCourseRoleRule.role_group_id == group.id,
                            TrainingCourseRoleRule.requirement_type == requirement_type,
                        ).first()
                        if rule is None:
                            rule = TrainingCourseRoleRule(
                                amo_id=job.amo_id,
                                course_id=course.id,
                                role_group_id=group.id,
                                requirement_type=requirement_type,
                            )
                            work_db.add(rule)
                        rule.is_required = bool(payload.get("is_required", True))
                        rule.notes = payload.get("notes")
                        rule.is_active = True
                        rule.source_job_id = job.id
                        work_db.flush()
                        item.committed_entity_id = rule.id
                        if group.code == "ALL":
                            canonical = work_db.query(training_models.TrainingRequirement).filter(
                                training_models.TrainingRequirement.amo_id == job.amo_id,
                                training_models.TrainingRequirement.course_id == course.id,
                                training_models.TrainingRequirement.scope == training_models.TrainingRequirementScope.ALL,
                            ).first()
                            any_required = work_db.query(TrainingCourseRoleRule.id).filter(
                                TrainingCourseRoleRule.amo_id == job.amo_id,
                                TrainingCourseRoleRule.course_id == course.id,
                                TrainingCourseRoleRule.role_group_id == group.id,
                                TrainingCourseRoleRule.is_active.is_(True),
                                TrainingCourseRoleRule.is_required.is_(True),
                            ).first() is not None
                            if canonical is None and any_required:
                                canonical = training_models.TrainingRequirement(
                                    amo_id=job.amo_id,
                                    course_id=course.id,
                                    scope=training_models.TrainingRequirementScope.ALL,
                                    is_mandatory=True,
                                    is_active=True,
                                    created_by_user_id=job.actor_user_id,
                                )
                                work_db.add(canonical)
                            elif canonical is not None:
                                canonical.is_mandatory = any_required
                                canonical.is_active = any_required
                total_processed += 1
                if index % 10 == 0 or index == len(matrix_rows):
                    _commit_progress(job.id, total_processed, "COMMITTING_COURSE_MATRIX", "tblCourseMatrix", item.display_label)

            training_rows_all = rows_by_sheet.get("Training", [])
            if training_rows_all:
                _commit_progress(job.id, total_processed, "COMMITTING_TRAINING", "Training", None)
            training_payloads: list[dict[str, Any]] = []
            training_rows: list[TrainingWorkbookImportRow] = []
            for item in training_rows_all:
                if item.status == "FAILED" or (item.decision or "").upper() == "SKIP":
                    total_processed += 1
                    continue
                training_payloads.append({"row_number": item.source_row, **dict(item.payload_json or {})})
                training_rows.append(item)
            if training_payloads:
                result = records_import.import_training_records_rows(
                    work_db,
                    amo_id=job.amo_id,
                    rows=training_payloads,
                    dry_run=False,
                    actor_user_id=job.actor_user_id,
                    manage_transaction=False,
                    progress_callback=_progress_callback(job.id, total_processed),
                )
                preview_by_row = {entry.row_number: entry for entry in result.preview_rows}
                for item in training_rows:
                    preview = preview_by_row.get(item.source_row)
                    if preview:
                        item.committed_entity_id = preview.existing_record_id
                        item.proposed_action = preview.action
                        if preview.action == "SKIP":
                            item.status = "FAILED"
                            item.issue_message = preview.reason
                total_processed += len(training_payloads)
            if training_rows_all:
                _commit_progress(job.id, total_processed, "COMMITTING_TRAINING", "Training", training_rows_all[-1].display_label)

            audit_services.log_event(
                work_db,
                amo_id=job.amo_id,
                actor_user_id=job.actor_user_id,
                entity_type="training.workbook_import",
                entity_id=job.id,
                action="COMMIT",
                after={"filename": job.filename, "sha256": job.file_sha256, "rows": total_processed},
                metadata={"module": "training", "source": "Training_Tracker workbook"},
                critical=True,
            )

        # Persist row-result markers only after the operational transaction has
        # committed. Detached objects cannot have been flushed by progress jobs.
        for item in rows:
            persisted = progress_db.get(TrainingWorkbookImportRow, item.id)
            if persisted:
                persisted.status = item.status if item.status in {"FAILED", "SKIPPED"} else "COMMITTED"
                persisted.issue_code = item.issue_code
                persisted.issue_message = item.issue_message
                persisted.committed_entity_id = item.committed_entity_id
                persisted.proposed_action = item.proposed_action
                progress_db.add(persisted)
        progress_db.commit()

        completed_job = progress_db.get(TrainingWorkbookImportJob, job.id)
        if not completed_job:
            return
        committed_rows = progress_db.query(TrainingWorkbookImportRow).filter(
            TrainingWorkbookImportRow.job_id == completed_job.id,
        ).all()
        completed_job.created_count = sum(1 for item in committed_rows if item.status == "COMMITTED" and item.proposed_action == "CREATE")
        completed_job.updated_count = sum(1 for item in committed_rows if item.status == "COMMITTED" and item.proposed_action == "UPDATE")
        completed_job.unchanged_count = sum(1 for item in committed_rows if item.status == "COMMITTED" and item.proposed_action == "UNCHANGED")
        completed_job.skipped_count = sum(1 for item in committed_rows if item.status == "SKIPPED")
        completed_job.failed_count = sum(1 for item in committed_rows if item.status == "FAILED")
        completed_job.review_count = 0
        completed_job.processed_rows = completed_job.total_rows
        completed_job.status = "COMPLETED"
        completed_job.stage = "COMPLETED"
        completed_job.current_sheet = None
        completed_job.current_record_label = None
        completed_job.committed_by_user_id = completed_job.actor_user_id
        completed_job.committed_at = utcnow()
        completed_job.completed_at = utcnow()
        progress_db.add(completed_job)
        progress_db.commit()
    except ImportReviewRequired as exc:
        work_db.rollback()
        progress_db.rollback()
        review_row = progress_db.get(TrainingWorkbookImportRow, exc.row_id)
        if review_row:
            review_row.status = "REVIEW"
            review_row.decision = None
            review_row.decision_required = True
            review_row.decision_options = exc.decision_options
            review_row.issue_code = exc.issue_code
            review_row.issue_message = exc.message
            review_row.committed_entity_id = None
            review_row.updated_at = utcnow()
            progress_db.add(review_row)
        review_job = progress_db.get(TrainingWorkbookImportJob, job_id)
        if review_job:
            review_job.status = "REVIEW_REQUIRED"
            review_job.stage = "REVIEW"
            review_job.current_sheet = "People"
            review_job.current_record_label = review_row.display_label if review_row else None
            review_job.error_message = exc.message
            review_job.completed_at = utcnow()
            progress_db.flush()
            review_job.review_count = progress_db.query(TrainingWorkbookImportRow).filter(
                TrainingWorkbookImportRow.job_id == review_job.id,
                TrainingWorkbookImportRow.decision_required.is_(True),
                TrainingWorkbookImportRow.decision.is_(None),
            ).count()
            progress_db.add(review_job)
        progress_db.commit()
    except Exception as exc:
        work_db.rollback()
        progress_db.rollback()
        failed_job = progress_db.get(TrainingWorkbookImportJob, job_id)
        if failed_job:
            if str(exc) == "IMPORT_CANCELLED":
                failed_job.status = "CANCELLED"
                failed_job.stage = "CANCELLED"
            else:
                failed_job.status = "FAILED"
                failed_job.stage = "FAILED"
                failed_job.error_message = str(exc)
            failed_job.completed_at = utcnow()
            progress_db.add(failed_job)
            progress_db.commit()
    finally:
        work_db.close()
        progress_db.close()


def _commit_progress(job_id: str, processed: int, stage: str, sheet: str, label: Optional[str]) -> None:
    db = SessionLocal()
    try:
        job = db.get(TrainingWorkbookImportJob, job_id)
        if not job:
            return
        job.processed_rows = min(job.total_rows, processed)
        job.stage = stage
        job.current_sheet = sheet
        job.current_record_label = (label or "")[:255] or None
        job.updated_at = utcnow()
        db.add(job)
        db.commit()
        if job.cancel_requested:
            raise RuntimeError("IMPORT_CANCELLED")
    finally:
        db.close()
'''
if not commit_pattern.search(text):
    raise RuntimeError("Could not locate commit function")
text = commit_pattern.sub(commit_replacement, text, count=1)
write(path, text)


# ---------------------------------------------------------------------------
# Frontend retry and progress stages.
# ---------------------------------------------------------------------------
path = "frontend/src/components/training/TrainingWorkbookImportDialog.tsx"
text = read(path)
text = text.replace('    USE_IMPORTED_EMAIL: "Use workbook email",\n', '')
text = text.replace('    RETRY_AFTER_PERSON_IMPORT: "Retry after accepted People rows are created",\n', '')
text = replace_once(
    text,
    '    COMMITTING_PEOPLE: "Writing personnel and licences",\n    COMMITTING_TRAINING: "Writing training history",\n',
    '    COMMITTING_PEOPLE: "Writing personnel and licences",\n    COMMITTING_ROLE_GROUPS: "Writing applicability groups",\n    COMMITTING_PERSON_ROLES: "Writing personnel role assignments",\n    COMMITTING_COURSE_MATRIX: "Writing course requirement matrix",\n    COMMITTING_TRAINING: "Writing training history",\n',
    "frontend progress stage labels",
)
text = replace_once(
    text,
    '  const isReviewReady = job?.status === "PREVIEW_READY" || job?.status === "REVIEW_REQUIRED";\n',
    '  const isReviewReady = job?.status === "PREVIEW_READY" || job?.status === "REVIEW_REQUIRED" || (job?.status === "FAILED" && Boolean(job.preview_completed_at));\n',
    "failed retry predicate",
)
error_anchor = '''        {error ? <div className="training-import-alert training-import-alert--danger"><XCircle size={18} /><span>{error}</span></div> : null}
'''
error_replacement = '''        {job?.status === "FAILED" && job.error_message ? (
          <div className="training-import-alert training-import-alert--danger">
            <XCircle size={18} />
            <span><strong>Previous commit attempt failed.</strong> {job.error_message} Review the retained decisions and retry when ready.</span>
          </div>
        ) : null}
        {error ? <div className="training-import-alert training-import-alert--danger"><XCircle size={18} /><span>{error}</span></div> : null}
'''
text = replace_once(text, error_anchor, error_replacement, "failed reason alert")
text = replace_once(
    text,
    '{committing ? "Starting import…" : `Commit ${Math.max(0, total - job.failed_count - job.skipped_count).toLocaleString()} reviewed rows`}',
    '{committing ? "Starting import…" : job.status === "FAILED" ? "Retry reviewed import" : `Commit ${Math.max(0, total - job.failed_count - job.skipped_count).toLocaleString()} reviewed rows`}',
    "retry button label",
)
write(path, text)


# ---------------------------------------------------------------------------
# Focused pure-logic regression tests.
# ---------------------------------------------------------------------------
path = "backend/amodb/apps/training/tests/test_workbook_import_mapping.py"
text = read(path)
text = text.replace(
    "from amodb.apps.training.workbook_import import WORKBOOK_SHEETS, _course_payload, _default_frequency_months, _person_payload, _workbook_params",
    "from amodb.apps.training.workbook_import import (\n    WORKBOOK_SHEETS,\n    _course_payload,\n    _default_frequency_months,\n    _identity_change_options,\n    _person_payload,\n    _retired_licence_status,\n    _should_materialize_catalogue_fallback,\n    _workbook_params,\n)",
)
append = '''


def test_create_account_race_returns_to_explicit_identity_review():
    assert _identity_change_options(
        has_same_person_account=True,
        has_conflicting_email_owner=False,
    ) == ["LINK_EXISTING_ACCOUNT", "KEEP_EXISTING_EMAIL", "SKIP"]
    assert _identity_change_options(
        has_same_person_account=False,
        has_conflicting_email_owner=True,
    ) == ["SKIP"]


def test_licence_reconciliation_distinguishes_replacement_from_removal():
    assert _retired_licence_status("KCAA/AMEL/NEW") == "SUPERSEDED"
    assert _retired_licence_status(None) == "RETIRED"
    assert _retired_licence_status("  ") == "RETIRED"


def test_catalogue_fallback_is_materialized_only_before_first_required_all_rule():
    assert _should_materialize_catalogue_fallback(
        has_active_requirements=False,
        has_required_all_rule=True,
    ) is True
    assert _should_materialize_catalogue_fallback(
        has_active_requirements=True,
        has_required_all_rule=True,
    ) is False
    assert _should_materialize_catalogue_fallback(
        has_active_requirements=False,
        has_required_all_rule=False,
    ) is False
'''
if "test_create_account_race_returns_to_explicit_identity_review" not in text:
    text += append
write(path, text)


# Documentation must describe replacement and retry semantics accurately.
path = "docs/training/TRAINING_TRACKER_WORKBOOK_MAPPING.md"
text = read(path)
if "Superseded licence numbers" not in text:
    text += '''

## Reconciliation guarantees

- A `CREATE_ACCOUNT` or `PROFILE_ONLY` decision is revalidated immediately before commit. An account created after preview returns the row to review and rolls back the operational transaction.
- Superseded licence numbers remain as historical records with `SUPERSEDED` status; cleared authority numbers are marked `RETIRED`. Only the current authority credential remains active/primary.
- Before the first required `ALL` matrix rule creates explicit canonical requirements, all active mandatory catalogue courses are materialized so the legacy mandatory-course fallback is not partially lost.
- Progress is published from isolated sessions. Row-result markers are persisted only after the operational transaction commits.
- Failed commit attempts retain review decisions and can be retried from the same import job.
'''
write(path, text)


subprocess.run(
    [
        "python",
        "-m",
        "py_compile",
        "backend/amodb/apps/training/workbook_import.py",
        "backend/amodb/apps/training/tests/test_workbook_import_mapping.py",
    ],
    cwd=ROOT,
    check=True,
)
