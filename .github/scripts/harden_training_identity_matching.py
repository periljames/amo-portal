from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "backend/amodb/apps/training/workbook_import.py"
text = path.read_text(encoding="utf-8")

old_conflict = '''            conflict = existing_profile and email_profile and existing_profile.id != email_profile.id
            user_conflict = existing_user and email_user and existing_user.id != email_user.id
            if conflict or user_conflict:
'''
new_conflict = '''            profile_email_conflict = bool(
                email_profile
                and upper(email_profile.person_id) != payload["person_id"]
            )
            user_email_conflict = bool(
                email_user
                and upper(email_user.staff_code) != payload["person_id"]
            )
            split_profile_conflict = bool(
                existing_profile
                and email_profile
                and existing_profile.id != email_profile.id
            )
            split_user_conflict = bool(
                existing_user
                and email_user
                and existing_user.id != email_user.id
            )
            if profile_email_conflict or user_email_conflict or split_profile_conflict or split_user_conflict:
'''
if old_conflict not in text:
    raise RuntimeError("Identity conflict preview block not found")
text = text.replace(old_conflict, new_conflict, 1)

old_selected = '''    imported_email = payload.get("email")
    selected_email = profile.email if decision == "KEEP_EXISTING_EMAIL" and profile.email else imported_email or profile.email
'''
new_selected = '''    imported_email = payload.get("email")
    selected_email = profile.email if decision == "KEEP_EXISTING_EMAIL" else imported_email or profile.email
'''
if old_selected not in text:
    raise RuntimeError("Email decision block not found")
text = text.replace(old_selected, new_selected, 1)

path.write_text(text, encoding="utf-8")
subprocess.run(["python", "-m", "py_compile", str(path)], cwd=ROOT, check=True)
