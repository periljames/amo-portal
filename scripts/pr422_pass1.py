from pathlib import Path
import re

path = Path("backend/amodb/apps/training/workbook_import.py")
text = path.read_text(encoding="utf-8")


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)


# Imported workbook data must not grant an account role or alter an existing
# user's authorization department.
role_line = '            role=_role_from_position(payload.get("position_title")),'
if text.count(role_line) != 2:
    raise RuntimeError("expected two imported role assignments")
text = text.replace(role_line, '            role=account_models.AccountRole.TECHNICIAN,')
one('            user.department_id = _department_id(db, job.amo_id, payload.get("department")) or user.department_id\n', '', "authorization department")

# The position-to-role helper is no longer safe or used.
text, count = re.subn(
    r"\n\ndef _role_from_position\(position: Optional\[str\]\) -> account_models\.AccountRole:\n.*?\n    return mapping\.get\(text, account_models\.AccountRole\.TECHNICIAN\)\n",
    "",
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("role inference helper was not found")

# Convert every commit-time identity collision into explicit re-review.
one(
    '    profile.birth_place = payload.get("birth_place")\n    db.flush()\n\n    existing_profile_user = db.get(account_models.User, profile.user_id) if profile.user_id else None',
    '    profile.birth_place = payload.get("birth_place")\n    try:\n        db.flush()\n    except IntegrityError as exc:\n        raise PersonnelIdentityChanged(row.id, "Personnel identity changed after preview. Review this People row again.") from exc\n\n    existing_profile_user = db.get(account_models.User, profile.user_id) if profile.user_id else None',
    "profile flush race",
)
one(
    '            raise ValueError("A portal account now exists for this person. Re-run preview and choose LINK_EXISTING_ACCOUNT or another reviewed action.")',
    '            raise PersonnelIdentityChanged(row.id, "A portal account now exists for this person. Review this People row again.")',
    "profile-only race",
)
one(
    '    _upsert_licence(db, job=job, profile=profile, user=user, authority="GHANA_CAA", country="Ghana", number=payload.get("g_amel"), category=None, category_source=None, payload=payload, source_row=row.source_row, primary=False)\n    db.flush()\n    return str(user.id if user else profile.id), "CREATE" if is_new else "UPDATE"',
    '    _upsert_licence(db, job=job, profile=profile, user=user, authority="GHANA_CAA", country="Ghana", number=payload.get("g_amel"), category=None, category_source=None, payload=payload, source_row=row.source_row, primary=False)\n    try:\n        db.flush()\n    except IntegrityError as exc:\n        raise PersonnelIdentityChanged(row.id, "Identity or licence state changed after preview. Review this People row again.") from exc\n    return str(user.id if user else profile.id), "CREATE" if is_new else "UPDATE"',
    "final identity flush race",
)

# Claim the worker exactly once and observe cancellation before any writes.
one(
    '        job = progress_db.get(TrainingWorkbookImportJob, job_id)\n        if not job:\n            return\n        duplicate = progress_db.query(TrainingWorkbookImportJob).filter(',
    '        job = (\n            progress_db.query(TrainingWorkbookImportJob)\n            .filter(TrainingWorkbookImportJob.id == job_id)\n            .with_for_update()\n            .first()\n        )\n        if not job or job.status != "QUEUED_COMMIT":\n            return\n        if job.cancel_requested:\n            raise RuntimeError("IMPORT_CANCELLED")\n        duplicate = progress_db.query(TrainingWorkbookImportJob).filter(',
    "worker claim",
)

# A review-required job is not completed.
old = '            job.completed_at = utcnow()\n            progress_db.add(job)\n            progress_db.commit()'
if old not in text:
    raise RuntimeError("commit exception completion marker not found")
head, tail = text.rsplit(old, 1)
text = head + '            job.completed_at = None if isinstance(exc, PersonnelIdentityChanged) else utcnow()\n            progress_db.add(job)\n            progress_db.commit()' + tail

path.write_text(text, encoding="utf-8")
