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


# Batch preview persistence: users still see row progress every ten records,
# while the backend avoids thousands of tiny commits for a normal tracker.
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
text = text.replace("                total_rows=len(rows),\n", "                total_rows=operational_rows if config[\"operational\"] else len(rows),\n", 1)
write(path, text)


# Include all imported matrix tables in the rolling-deployment guard.
path = "backend/amodb/apps/training/compliance.py"
text = read(path)
text = text.replace(
    'if inspector.has_table("training_role_groups") and inspector.has_table("training_course_role_rules"):',
    'if (\n        inspector.has_table("training_role_groups")\n        and inspector.has_table("training_person_roles")\n        and inspector.has_table("training_course_role_rules")\n    ):',
)
write(path, text)


# Show records from the sheet currently being processed, rather than applying a
# global offset to an alphabetically sorted multi-sheet result set.
path = "frontend/src/components/training/TrainingWorkbookImportDialog.tsx"
text = read(path)
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
text = replace_once(text, old_recent, new_recent, "current-sheet live records")
write(path, text)


# A completed import must invalidate both user and Training service caches before
# the module reloads, otherwise the new workbook data can remain invisible for
# several minutes despite a successful commit.
path = "frontend/src/pages/TrainingCompetencePage.tsx"
text = read(path)
text = text.replace(
    'import { listAdminUserSummaries, type AdminUserSummaryRead } from "../services/adminUsers";',
    'import { invalidateAdminUserCache, listAdminUserSummaries, type AdminUserSummaryRead } from "../services/adminUsers";',
)
training_import_anchor = "  getTrainingReportSettings,\n"
if "  invalidateTrainingServiceCache,\n" not in text:
    text = replace_once(text, training_import_anchor, training_import_anchor + "  invalidateTrainingServiceCache,\n", "training cache invalidator import")
old_completed = '''        onCompleted={async () => {
          await load();
        }}
'''
new_completed = '''        onCompleted={async () => {
          invalidateAdminUserCache();
          invalidateTrainingServiceCache();
          try {
            window.sessionStorage.removeItem(trainingDashboardSnapshotKey(amoCode));
          } catch {
            // Ignore storage failures; the fresh API load remains authoritative.
          }
          await load();
        }}
'''
text = replace_once(text, old_completed, new_completed, "post-import cache refresh")
write(path, text)


# Keep the mapping contract explicit about inactive personnel identities that
# retain history without granting access.
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
    ],
    cwd=ROOT,
    check=True,
)
