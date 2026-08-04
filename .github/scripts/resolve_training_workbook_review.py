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
# Workbook preview efficiency and exact progress totals.
# ---------------------------------------------------------------------------
path = "backend/amodb/apps/training/workbook_import.py"
text = read(path)
old_progress = '''    job.updated_at = utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    if job.cancel_requested:
        raise RuntimeError("IMPORT_CANCELLED")
'''
new_progress = '''    job.updated_at = utcnow()
    db.add(job)
    should_publish = job.processed_rows % 10 == 0 or job.processed_rows >= job.total_rows
    if should_publish:
        db.commit()
        db.refresh(job)
        if job.cancel_requested:
            raise RuntimeError("IMPORT_CANCELLED")
    else:
        db.flush()
'''
text = replace_once(text, old_progress, new_progress, "batched preview progress")

old_discovery = '''            rows = _sheet_rows(workbook[name])
            rows_by_sheet[name] = rows
            operational_rows = len(rows) if config["operational"] else 0
            total_rows += operational_rows
            sheet = TrainingWorkbookImportSheet(
'''
new_discovery = '''            rows = _sheet_rows(workbook[name])
            rows_by_sheet[name] = rows
            if name == "People":
                operational_rows = sum(1 for row in rows if upper(row.get("PersonID")) != "TOTAL")
            else:
                operational_rows = len(rows) if config["operational"] else 0
            total_rows += operational_rows
            sheet = TrainingWorkbookImportSheet(
'''
text = replace_once(text, old_discovery, new_discovery, "exact operational row total")
text = replace_once(
    text,
    "                total_rows=len(rows),\n",
    "                total_rows=operational_rows if config[\"operational\"] else len(rows),\n",
    "sheet manifest row total",
)

# Identity conflicts cannot safely claim an email already owned by another
# profile/account. Keep the existing identity or skip and resolve externally.
text = text.replace(
    'decision_options=["KEEP_EXISTING_EMAIL", "USE_IMPORTED_EMAIL", "SKIP"],',
    'decision_options=["KEEP_EXISTING_EMAIL", "SKIP"],',
)

# Distinguish a missing profile for an already-known account from a genuinely
# new person, so PROFILE_ONLY is never offered when an account already exists.
old_people_branch = '''                if profile and user:
                    action = "UPDATE" if change_list else "UNCHANGED"
                    item = _row(job_id=job.id, sheet="People", row_number=row_number, entity_type="PERSON", source_key=payload["person_id"], label=payload["full_name"], action=action, payload=payload, changes=change_list)
                    _counter(sheet, action)
                else:
                    action = "UPDATE" if profile else "CREATE"
                    options = ["PROFILE_ONLY", "SKIP"] if not payload["email"] else ["CREATE_ACCOUNT", "PROFILE_ONLY", "SKIP"]
                    item = _row(
                        job_id=job.id, sheet="People", row_number=row_number, entity_type="PERSON",
                        source_key=payload["person_id"], label=payload["full_name"], action=action, status="REVIEW",
                        decision_required=True, decision_options=options, payload=payload, changes=change_list,
                        issue_code="NEW_PERSON" if not profile else "ACCOUNT_NOT_LINKED",
                        issue_message="Review whether this person should receive portal access or remain a personnel-only record.",
                    )
                    _counter(sheet, action, review=True)
'''
new_people_branch = '''                if profile and user:
                    action = "UPDATE" if change_list else "UNCHANGED"
                    item = _row(job_id=job.id, sheet="People", row_number=row_number, entity_type="PERSON", source_key=payload["person_id"], label=payload["full_name"], action=action, payload=payload, changes=change_list)
                    _counter(sheet, action)
                elif user and not profile:
                    item = _row(
                        job_id=job.id,
                        sheet="People",
                        row_number=row_number,
                        entity_type="PERSON",
                        source_key=payload["person_id"],
                        label=payload["full_name"],
                        action="UPDATE",
                        status="REVIEW",
                        decision_required=True,
                        decision_options=["LINK_EXISTING_ACCOUNT", "SKIP"],
                        payload=payload,
                        changes=change_list,
                        issue_code="PROFILE_NOT_LINKED",
                        issue_message="A portal account exists for this staff code or email. Review and link the personnel profile, or skip the row.",
                    )
                    _counter(sheet, "UPDATE", review=True)
                else:
                    action = "UPDATE" if profile else "CREATE"
                    options = ["PROFILE_ONLY", "SKIP"] if not payload["email"] else ["CREATE_ACCOUNT", "PROFILE_ONLY", "SKIP"]
                    item = _row(
                        job_id=job.id, sheet="People", row_number=row_number, entity_type="PERSON",
                        source_key=payload["person_id"], label=payload["full_name"], action=action, status="REVIEW",
                        decision_required=True, decision_options=options, payload=payload, changes=change_list,
                        issue_code="NEW_PERSON" if not profile else "ACCOUNT_NOT_LINKED",
                        issue_message="Review whether this person should enter approval/onboarding or remain a non-login personnel identity.",
                    )
                    _counter(sheet, action, review=True)
'''
text = replace_once(text, old_people_branch, new_people_branch, "People review branching")

# Rewrite the personnel commit function so PROFILE_ONLY never updates or links
# a pre-existing portal account. It creates a separate inactive identity with a
# synthetic non-login address, allowing training history to retain a User FK.
person_pattern = re.compile(r"def _upsert_person\(.*?\n\ndef _progress_callback", re.S)
new_person_function = '''def _upsert_person(db: Session, job: TrainingWorkbookImportJob, row: TrainingWorkbookImportRow) -> tuple[Optional[str], str]:
    payload = dict(row.payload_json or {})
    person_id = upper(payload.get("person_id"))
    decision = (row.decision or "").upper()
    if decision == "SKIP":
        return None, "SKIP"
    if decision == "USE_IMPORTED_EMAIL":
        raise ValueError("Imported email conflicts must be reconciled outside the import; choose KEEP_EXISTING_EMAIL or SKIP.")

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

    imported_email = payload.get("email")
    selected_email = profile.email if decision == "KEEP_EXISTING_EMAIL" and profile.email else imported_email or profile.email

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

    existing_profile_user = db.get(account_models.User, profile.user_id) if profile.user_id else None
    existing_staff_user = db.query(account_models.User).filter(
        account_models.User.amo_id == job.amo_id,
        account_models.User.staff_code == person_id,
    ).first()
    existing_email_user = None
    if selected_email:
        existing_email_user = db.query(account_models.User).filter(
            account_models.User.amo_id == job.amo_id,
            func.lower(account_models.User.email) == str(selected_email).lower(),
        ).first()

    if decision == "PROFILE_ONLY":
        if existing_profile_user or existing_staff_user or existing_email_user:
            raise ValueError("A portal account now exists for this person. Re-run preview and choose LINK_EXISTING_ACCOUNT or another reviewed action.")
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
        db.add(user)
        db.flush()
        profile.user_id = user.id
    else:
        user = existing_profile_user or existing_staff_user or existing_email_user
        if user is None and decision == "CREATE_ACCOUNT":
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
            db.add(user)
            db.flush()
        elif user is None and decision == "LINK_EXISTING_ACCOUNT":
            raise ValueError("The account selected for linking no longer exists. Re-run the workbook preview.")
        elif user is not None:
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
        if user is not None:
            profile.user_id = user.id

    if user and payload.get("kamel_no"):
        user.regulatory_authority = account_models.RegulatoryAuthority.KCAA
        user.licence_number = payload.get("kamel_no")
        user.licence_state_or_country = "Kenya"

    category = payload.get("category_reg_2018") or payload.get("category_reg_2013")
    category_source = "Reg. 2018" if payload.get("category_reg_2018") else "Reg. 2013" if payload.get("category_reg_2013") else None
    _upsert_licence(db, job=job, profile=profile, user=user, authority="KCAA", country="Kenya", number=payload.get("kamel_no"), category=category, category_source=category_source, payload=payload, source_row=row.source_row, primary=True)
    _upsert_licence(db, job=job, profile=profile, user=user, authority="ETHIOPIAN_CAA", country="Ethiopia", number=payload.get("e_amel"), category=None, category_source=None, payload=payload, source_row=row.source_row, primary=False)
    _upsert_licence(db, job=job, profile=profile, user=user, authority="GHANA_CAA", country="Ghana", number=payload.get("g_amel"), category=None, category_source=None, payload=payload, source_row=row.source_row, primary=False)
    db.flush()
    return str(user.id if user else profile.id), "CREATE" if is_new else "UPDATE"


def _progress_callback'''
if not person_pattern.search(text):
    raise RuntimeError("Could not locate personnel commit function")
text = person_pattern.sub(new_person_function, text, count=1)

# Canonical ALL requirements must move both directions with the matrix.
old_all_rule = '''                # ALL rules also populate the canonical requirement table for existing consumers.
                if group.code == "ALL" and rule.is_required:
                    canonical = work_db.query(training_models.TrainingRequirement).filter(
                        training_models.TrainingRequirement.amo_id == job.amo_id,
                        training_models.TrainingRequirement.course_id == course.id,
                        training_models.TrainingRequirement.scope == training_models.TrainingRequirementScope.ALL,
                    ).first()
                    if canonical is None:
                        canonical = training_models.TrainingRequirement(
                            amo_id=job.amo_id, course_id=course.id, scope=training_models.TrainingRequirementScope.ALL,
                            is_mandatory=True, is_active=True, created_by_user_id=job.actor_user_id,
                        )
                        work_db.add(canonical)
                    else:
                        canonical.is_mandatory = True
                        canonical.is_active = True
'''
new_all_rule = '''                # Keep the canonical ALL requirement in exact sync for existing
                # consumers, including deactivation when a later matrix makes
                # the course optional.
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
'''
text = replace_once(text, old_all_rule, new_all_rule, "canonical ALL reconciliation")
write(path, text)


# Rolling deployment guard for every imported matrix table.
path = "backend/amodb/apps/training/compliance.py"
text = read(path)
text = text.replace(
    'if inspector.has_table("training_role_groups") and inspector.has_table("training_course_role_rules"):',
    'if (\n        inspector.has_table("training_role_groups")\n        and inspector.has_table("training_person_roles")\n        and inspector.has_table("training_course_role_rules")\n    ):',
)
write(path, text)


# ---------------------------------------------------------------------------
# Frontend: paginate every review decision, show current-sheet progress, and
# invalidate caches immediately after commit.
# ---------------------------------------------------------------------------
path = "frontend/src/components/training/TrainingWorkbookImportDialog.tsx"
text = read(path)
helper_anchor = '''function statusTone(status: string): string {
  if (["FAILED", "REVIEW"].includes(status)) return "danger";
  if (["COMPLETED", "COMMITTED", "READY"].includes(status)) return "success";
  if (["SKIPPED", "CANCELLED"].includes(status)) return "muted";
  return "info";
}

'''
helper = helper_anchor + '''async function loadAllImportRows(
  jobId: string,
  options: { reviewOnly?: boolean; status?: string },
): Promise<TrainingWorkbookImportRow[]> {
  const limit = 250;
  const items: TrainingWorkbookImportRow[] = [];
  let offset = 0;
  while (true) {
    const page = await listTrainingWorkbookImportRows(jobId, { ...options, limit, offset });
    items.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || page.items.length === 0) return items;
  }
}

'''
if "async function loadAllImportRows" not in text:
    text = replace_once(text, helper_anchor, helper, "all review rows helper")
old_recent = '''        const offset = Math.max(0, (next.processed_rows || 0) - 8);
        const page = await listTrainingWorkbookImportRows(next.id, { limit: 8, offset });
        if (!stopped) setRecentRows(page.items);
'''
new_recent = '''        const activeSheet = next.sheets.find((sheet) => sheet.sheet_name === next.current_sheet);
        const offset = Math.max(0, (activeSheet?.processed_rows || 0) - 8);
        const page = await listTrainingWorkbookImportRows(next.id, {
          sheet: next.current_sheet || undefined,
          limit: 8,
          offset,
        });
        if (!stopped) setRecentRows(page.items);
'''
text = replace_once(text, old_recent, new_recent, "current-sheet live rows")
old_pages = '''        const [reviewPage, issuePage] = await Promise.all([
          listTrainingWorkbookImportRows(job.id, { reviewOnly: true, limit: 250 }),
          listTrainingWorkbookImportRows(job.id, { status: "FAILED", limit: 250 }),
        ]);
        if (!active) return;
        setReviewRows(reviewPage.items);
        setIssueRows(issuePage.items);
        setDecisions((current) => {
          const next = { ...current };
          reviewPage.items.forEach((row) => {
'''
new_pages = '''        const [allReviewRows, allIssueRows] = await Promise.all([
          loadAllImportRows(job.id, { reviewOnly: true }),
          loadAllImportRows(job.id, { status: "FAILED" }),
        ]);
        if (!active) return;
        setReviewRows(allReviewRows);
        setIssueRows(allIssueRows);
        setDecisions((current) => {
          const next = { ...current };
          allReviewRows.forEach((row) => {
'''
text = replace_once(text, old_pages, new_pages, "review pagination")
text = text.replace(
    'CREATE_ACCOUNT: "Create inactive account for approval and onboarding",',
    'CREATE_ACCOUNT: "Create inactive account for approval and onboarding",\n    LINK_EXISTING_ACCOUNT: "Link the existing portal account to this personnel profile",',
)
text = text.replace(
    'New people are never silently activated. Create an inactive account for approval, keep a non-login personnel identity, or skip the row.',
    'New people are never silently activated. Create an inactive account for approval, link an existing account when identified, keep a non-login personnel identity, or skip the row.',
)
write(path, text)

path = "frontend/src/pages/TrainingCompetencePage.tsx"
text = read(path)
text = text.replace(
    'import { listAdminUserSummaries, type AdminUserSummaryRead } from "../services/adminUsers";',
    'import { invalidateAdminUserCache, listAdminUserSummaries, type AdminUserSummaryRead } from "../services/adminUsers";',
)
if "  invalidateTrainingServiceCache,\n" not in text:
    text = replace_once(text, "  getTrainingReportSettings,\n", "  getTrainingReportSettings,\n  invalidateTrainingServiceCache,\n", "Training cache invalidator import")
text = replace_once(
    text,
    '''        onCompleted={async () => {
          await load();
        }}
''',
    '''        onCompleted={async () => {
          invalidateAdminUserCache();
          invalidateTrainingServiceCache();
          try {
            window.sessionStorage.removeItem(trainingDashboardSnapshotKey(amoCode));
          } catch {
            // Ignore storage failures; the fresh API load remains authoritative.
          }
          await load();
        }}
''',
    "post-import cache refresh",
)
write(path, text)

path = "docs/training/TRAINING_TRACKER_WORKBOOK_MAPPING.md"
text = read(path)
text = text.replace(
    "A personnel-only profile is supported when a person must exist in training records but should not receive portal access.",
    "A personnel-only choice creates an inactive non-login identity linked to the personnel profile so licences and training history remain queryable without granting portal access.",
)
write(path, text)

subprocess.run(
    [
        "python",
        "-m",
        "py_compile",
        "backend/amodb/apps/training/workbook_import.py",
        "backend/amodb/apps/training/compliance.py",
        "backend/amodb/apps/training/workbook_router.py",
    ],
    cwd=ROOT,
    check=True,
)
