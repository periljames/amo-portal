from pathlib import Path

path = Path("backend/amodb/apps/training/workbook_import.py")
text = path.read_text(encoding="utf-8")


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)


# Publish the last partial batch for every dependency stage. This also checks
# cancellation when a sheet contains fewer rows than the periodic interval.
one('            for item in rows_by_sheet.get("Courses", []):', '            course_items = rows_by_sheet.get("Courses", [])\n            for item in course_items:', "course stage")
one('            # Personnel + explicit access decisions + multi-authority licences.', '            if course_items:\n                _commit_progress(progress_db, job.id, total_processed, "COMMITTING_COURSES", "Courses", course_items[-1].display_label)\n\n            # Personnel + explicit access decisions + multi-authority licences.', "course final progress")
one('            for item in rows_by_sheet.get("People", []):', '            people_items = rows_by_sheet.get("People", [])\n            for item in people_items:', "people stage")
one('            # Applicability groups.', '            if people_items:\n                _commit_progress(progress_db, job.id, total_processed, "COMMITTING_PEOPLE", "People", people_items[-1].display_label)\n\n            # Applicability groups.', "people final progress")
one('            groups: dict[str, TrainingRoleGroup] = {}\n            for item in rows_by_sheet.get("tblRoleGroups", []):', '            groups: dict[str, TrainingRoleGroup] = {}\n            role_group_items = rows_by_sheet.get("tblRoleGroups", [])\n            for item in role_group_items:', "role group stage")
one('            profiles = {upper(item.person_id): item for item in work_db.query(account_models.PersonnelProfile).filter(account_models.PersonnelProfile.amo_id == job.amo_id).all()}', '            if role_group_items:\n                _commit_progress(progress_db, job.id, total_processed, "COMMITTING_ROLE_GROUPS", "tblRoleGroups", role_group_items[-1].display_label)\n\n            profiles = {upper(item.person_id): item for item in work_db.query(account_models.PersonnelProfile).filter(account_models.PersonnelProfile.amo_id == job.amo_id).all()}', "role group final progress")
one('            for item in rows_by_sheet.get("tblPersonRoles", []):', '            person_role_items = rows_by_sheet.get("tblPersonRoles", [])\n            for item in person_role_items:', "person role stage")
one('            courses = {upper(item.course_id): item for item in work_db.query(training_models.TrainingCourse).filter(training_models.TrainingCourse.amo_id == job.amo_id).all()}', '            if person_role_items:\n                _commit_progress(progress_db, job.id, total_processed, "COMMITTING_PERSON_ROLES", "tblPersonRoles", person_role_items[-1].display_label)\n\n            courses = {upper(item.course_id): item for item in work_db.query(training_models.TrainingCourse).filter(training_models.TrainingCourse.amo_id == job.amo_id).all()}', "person role final progress")
one('            for item in rows_by_sheet.get("tblCourseMatrix", []):', '            matrix_items = rows_by_sheet.get("tblCourseMatrix", [])\n            for item in matrix_items:', "matrix stage")
one('            training_payloads = []', '            if matrix_items:\n                _commit_progress(progress_db, job.id, total_processed, "COMMITTING_COURSE_MATRIX", "tblCourseMatrix", matrix_items[-1].display_label)\n\n            training_payloads = []', "matrix final progress")

old_matrix = '''                if group.code == "ALL":
                    if bool(payload.get("is_required", True)):
                        _materialize_mandatory_catalogue_requirements(work_db, job)
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
new_matrix = '''                if group.code == "ALL":
                    # Materialize catalogue fallback before either a required or
                    # optional ALL rule switches this course into explicit mode.
                    _materialize_mandatory_catalogue_requirements(work_db, job)
                    canonicals = work_db.query(training_models.TrainingRequirement).filter(
                        training_models.TrainingRequirement.amo_id == job.amo_id,
                        training_models.TrainingRequirement.course_id == course.id,
                        training_models.TrainingRequirement.scope == training_models.TrainingRequirementScope.ALL,
                    ).all()
                    any_required = work_db.query(TrainingCourseRoleRule.id).filter(
                        TrainingCourseRoleRule.amo_id == job.amo_id,
                        TrainingCourseRoleRule.course_id == course.id,
                        TrainingCourseRoleRule.role_group_id == group.id,
                        TrainingCourseRoleRule.is_active.is_(True),
                        TrainingCourseRoleRule.is_required.is_(True),
                    ).first() is not None
                    # Keep fallback aligned if this leaves no active explicit
                    # requirements for the tenant.
                    course.is_mandatory = any_required
                    if not canonicals and any_required:
                        work_db.add(training_models.TrainingRequirement(
                            amo_id=job.amo_id,
                            course_id=course.id,
                            scope=training_models.TrainingRequirementScope.ALL,
                            is_mandatory=True,
                            is_active=True,
                            created_by_user_id=job.actor_user_id,
                        ))
                    else:
                        for canonical in canonicals:
                            canonical.is_mandatory = any_required
                            canonical.is_active = any_required
'''
one(old_matrix, new_matrix, "ALL rule reconciliation")

old_audit = '''            audit_services.log_event(
                work_db,
                amo_id=job.amo_id,
                actor_user_id=job.actor_user_id,
                entity_type="training.workbook_import",
                entity_id=job.id,
                action="COMMIT",
                after={"filename": job.filename, "sha256": job.file_sha256, "rows": total_processed},
                metadata={"module": "training", "source": "Training_Tracker workbook"},
            )
'''
new_audit = '''            audit_event = audit_services.log_event(
                work_db,
                amo_id=job.amo_id,
                actor_user_id=job.actor_user_id,
                entity_type="training.workbook_import",
                entity_id=job.id,
                action="COMMIT",
                after={"filename": job.filename, "sha256": job.file_sha256, "rows": total_processed},
                metadata={
                    "module": "training",
                    "source": "Training_Tracker workbook",
                    "forceReimport": force_reimport,
                },
            )
            if audit_event is None:
                raise RuntimeError("The Training workbook audit event could not be recorded.")
'''
one(old_audit, new_audit, "durable audit event")

path.write_text(text, encoding="utf-8")
