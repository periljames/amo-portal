from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "backend/amodb/apps/training/workbook_import.py"
text = path.read_text(encoding="utf-8")

old_options = '''                    decision_required=True, decision_options=["KEEP_EXISTING_EMAIL", "SKIP"],
                    payload=payload, issue_code="IDENTITY_CONFLICT",
'''
new_options = '''                    decision_required=True,
                    decision_options=["KEEP_EXISTING_EMAIL", "SKIP"] if (existing_profile or existing_user) else ["SKIP"],
                    payload=payload, issue_code="IDENTITY_CONFLICT",
'''
if old_options not in text:
    raise RuntimeError("Identity conflict decision options not found")
text = text.replace(old_options, new_options, 1)

old_identity = '''    profile_by_person = db.query(account_models.PersonnelProfile).filter(
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
'''
new_identity = '''    profile_by_person = db.query(account_models.PersonnelProfile).filter(
        account_models.PersonnelProfile.amo_id == job.amo_id,
        account_models.PersonnelProfile.person_id == person_id,
    ).first()
    profile_by_email = None
    if payload.get("email"):
        profile_by_email = db.query(account_models.PersonnelProfile).filter(
            account_models.PersonnelProfile.amo_id == job.amo_id,
            func.lower(account_models.PersonnelProfile.email) == str(payload["email"]).lower(),
        ).first()
    existing_staff_user = db.query(account_models.User).filter(
        account_models.User.amo_id == job.amo_id,
        account_models.User.staff_code == person_id,
    ).first()
    profile = profile_by_person if decision == "KEEP_EXISTING_EMAIL" else profile_by_person or profile_by_email
    is_new = profile is None
'''
if old_identity not in text:
    raise RuntimeError("Personnel identity selection block not found")
text = text.replace(old_identity, new_identity, 1)

old_selected = '''    imported_email = payload.get("email")
    selected_email = profile.email if decision == "KEEP_EXISTING_EMAIL" else imported_email or profile.email
'''
new_selected = '''    imported_email = payload.get("email")
    if decision == "KEEP_EXISTING_EMAIL":
        selected_email = (profile_by_person.email if profile_by_person else None) or (existing_staff_user.email if existing_staff_user else None)
    else:
        selected_email = imported_email or profile.email
'''
if old_selected not in text:
    raise RuntimeError("Selected email block not found")
text = text.replace(old_selected, new_selected, 1)

old_users = '''    existing_profile_user = db.get(account_models.User, profile.user_id) if profile.user_id else None
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
'''
new_users = '''    existing_profile_user = db.get(account_models.User, profile.user_id) if profile.user_id else None
    existing_email_user = None
    if selected_email and decision != "KEEP_EXISTING_EMAIL":
        existing_email_user = db.query(account_models.User).filter(
            account_models.User.amo_id == job.amo_id,
            func.lower(account_models.User.email) == str(selected_email).lower(),
        ).first()
'''
if old_users not in text:
    raise RuntimeError("Existing user lookup block not found")
text = text.replace(old_users, new_users, 1)

path.write_text(text, encoding="utf-8")
subprocess.run(["python", "-m", "py_compile", str(path)], cwd=ROOT, check=True)
