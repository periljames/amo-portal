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


# 1. Register the workbook sub-router without creating a circular import.
path = "backend/amodb/apps/training/router.py"
text = read(path)
marker = "# TRAINING_WORKBOOK_CONTROL_CENTRE"
if marker not in text:
    text += "\n\n# TRAINING_WORKBOOK_CONTROL_CENTRE\nfrom .workbook_router import router as training_workbook_import_router\n\nrouter.include_router(training_workbook_import_router)\n"
write(path, text)


# 2. Keep the proven record lifecycle importer, but allow the governed workbook
# transaction to own commit/rollback and publish real row progress.
path = "backend/amodb/apps/training/records_import.py"
text = read(path)
text = text.replace("from typing import Any, Dict, Iterable, Optional", "from typing import Any, Callable, Dict, Iterable, Optional")
old_signature = '''def import_training_records_rows(
    db: Session,
    *,
    amo_id: str,
    rows: list[dict[str, Any]],
    dry_run: bool,
    actor_user_id: Optional[str] = None,
) -> schemas.TrainingRecordImportSummary:'''
new_signature = '''def import_training_records_rows(
    db: Session,
    *,
    amo_id: str,
    rows: list[dict[str, Any]],
    dry_run: bool,
    actor_user_id: Optional[str] = None,
    manage_transaction: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> schemas.TrainingRecordImportSummary:'''
if old_signature in text:
    text = replace_once(text, old_signature, new_signature, "record importer signature")
loop_old = "    for parsed, user, course in matched_pairs:\n"
loop_new = '''    for processed_index, (parsed, user, course) in enumerate(matched_pairs, start=1):
        if progress_callback:
            progress_callback(
                processed_index,
                len(matched_pairs),
                f"{parsed.person_name or parsed.person_id} · {parsed.course_id}",
            )
'''
if loop_old in text:
    text = replace_once(text, loop_old, loop_new, "record importer progress loop")
commit_old = '''    if not dry_run:
        for record in existing_by_key.values():
            if record.id in lifecycle_status_by_id:
                db.add(record)
        db.commit()
'''
commit_new = '''    if not dry_run:
        for record in existing_by_key.values():
            if record.id in lifecycle_status_by_id:
                db.add(record)
        if manage_transaction:
            db.commit()
'''
if commit_old in text:
    text = replace_once(text, commit_old, commit_new, "record importer transaction ownership")
write(path, text)


# 3. Standalone People imports must understand the real workbook KAMEL heading.
path = "backend/amodb/apps/accounts/personnel_import.py"
text = read(path)
text = text.replace('amel_no=_to_clean_str(raw.get("AMEL NO:")),', 'amel_no=_to_clean_str(raw.get("KAMEL NO:")) or _to_clean_str(raw.get("AMEL NO:")),')
write(path, text)


# 4. Make workbook role groups and matrix rules authoritative inputs to the
# existing compliance engine instead of leaving them as decorative imports.
path = "backend/amodb/apps/training/compliance.py"
text = read(path)
import_anchor = "from . import models as training_models\n"
if "from . import workbook_models as training_workbook_models" not in text:
    text = replace_once(text, import_anchor, import_anchor + "from . import workbook_models as training_workbook_models\n", "compliance workbook import")
return_anchor = "    return sorted(set(required_course_ids))\n"
role_logic = '''    # Role groups and matrix rules imported from the governed Training Tracker
    # extend the canonical ALL/DEPARTMENT/JOB_ROLE/USER requirement model.  This
    # preserves exact workbook applicability (including multi-role personnel)
    # without using brittle position-name heuristics in the frontend.
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

    return sorted(set(required_course_ids))
'''
if role_logic not in text:
    text = replace_once(text, return_anchor, role_logic, "compliance role matrix")
write(path, text)


# 5. Replace the two legacy synchronous importer controls with one governed
# multi-sheet workflow.  Remove byte-only state and raw JSON rendering.
path = "frontend/src/pages/TrainingCompetencePage.tsx"
text = read(path)
if 'TrainingWorkbookImportDialog' not in text:
    text = replace_once(
        text,
        'import Drawer from "../components/shared/Drawer";\n',
        'import Drawer from "../components/shared/Drawer";\nimport TrainingWorkbookImportDialog from "../components/training/TrainingWorkbookImportDialog";\n',
        "training page importer component",
    )
for token in [
    "  importTrainingCoursesWorkbook,\n",
    "  importTrainingRecordsWorkbook,\n",
    "  type TransferProgress,\n",
]:
    text = text.replace(token, "")
state_old = '''  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<"courses" | "trainings">("courses");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importDryRun, setImportDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<TransferProgress | null>(null);
  const [importSummary, setImportSummary] = useState<any | null>(null);
'''
if state_old in text:
    text = replace_once(text, state_old, '  const [workbookImportOpen, setWorkbookImportOpen] = useState(false);\n', "training page import state")
run_pattern = re.compile(r"\n  const runImport = async \(\) => \{.*?\n  \};\n\n  const exportCourses", re.S)
if run_pattern.search(text):
    text = run_pattern.sub("\n  const exportCourses", text, count=1)
action_old = '''              <button type="button" className="secondary-chip-btn" onClick={() => { setImportMode("courses"); setImportOpen(true); }}><Upload size={14} /> Import courses</button>
              <button type="button" className="secondary-chip-btn" onClick={() => { setImportMode("trainings"); setImportOpen(true); }}><Upload size={14} /> Import trainings</button>'''
action_new = '''              <button type="button" className="primary-chip-btn" onClick={() => setWorkbookImportOpen(true)}><Upload size={14} /> Import workbook</button>'''
if action_old in text:
    text = replace_once(text, action_old, action_new, "training page import actions")
drawer_pattern = re.compile(
    r"\n\s*<Drawer title=\{importMode === \"courses\" \? \"Import courses workbook\" : \"Import trainings workbook\"\}.*?</Drawer>",
    re.S,
)
replacement = '''

      <TrainingWorkbookImportDialog
        isOpen={workbookImportOpen}
        onClose={() => setWorkbookImportOpen(false)}
        onCompleted={async () => {
          await load();
        }}
      />'''
if drawer_pattern.search(text):
    text = drawer_pattern.sub(replacement, text, count=1)
write(path, text)


# 6. Put all imported KCAA/Ethiopia/Ghana licences directly on the personnel
# training profile, with the existing single User licence as a safe fallback.
path = "frontend/src/pages/QMSTrainingUserPage.tsx"
text = read(path)
if 'PersonnelLicencePanel' not in text:
    text = replace_once(
        text,
        'import QMSLayout from "../components/QMS/QMSLayout";\n',
        'import QMSLayout from "../components/QMS/QMSLayout";\nimport PersonnelLicencePanel from "../components/training/PersonnelLicencePanel";\n',
        "training profile licence component",
    )
hero_anchor = '''              </div>
            </div>

            <div className="training-profile-toolbar training-profile-toolbar--surface">'''
hero_replacement = '''              </div>
              <PersonnelLicencePanel
                userId={user.id}
                fallback={{
                  authority: user.regulatory_authority,
                  licenceNumber: user.licence_number,
                  country: user.licence_state_or_country,
                  expiresOn: user.licence_expires_on,
                }}
              />
            </div>

            <div className="training-profile-toolbar training-profile-toolbar--surface">'''
if hero_anchor in text and "<PersonnelLicencePanel" not in text:
    text = replace_once(text, hero_anchor, hero_replacement, "training profile licence panel")
write(path, text)


# 7. Avoid one-segment dynamic-route collisions for role catalogue reads.
path = "backend/amodb/apps/training/workbook_router.py"
text = read(path)
text = text.replace('@router.get("/role-groups",', '@router.get("/catalog/role-groups",')
text = text.replace('@router.get("/role-rules",', '@router.get("/catalog/role-rules",')
text = text.replace('@router.get("/people/{user_id}/roles",', '@router.get("/users/{user_id}/roles",')
write(path, text)


# 8. Focused import test command is intentionally lightweight.  Full backend
# and browser suites continue in repository CI.
subprocess.run(
    ["python", "-m", "py_compile",
     "backend/amodb/apps/training/workbook_models.py",
     "backend/amodb/apps/training/workbook_schemas.py",
     "backend/amodb/apps/training/workbook_import.py",
     "backend/amodb/apps/training/workbook_router.py",
     "backend/amodb/apps/training/records_import.py"],
    cwd=ROOT,
    check=True,
)

# Remove the one-shot workflow machinery before committing the product code.
(ROOT / ".github/workflows/training-workbook-control-centre.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)

subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
subprocess.run(["git", "commit", "-m", "Build governed Training workbook control centre"], cwd=ROOT, check=True)
subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)
