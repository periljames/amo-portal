from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend/src/pages/QMSTrainingUserPage.tsx"
BACKEND = ROOT / "backend/amodb/apps/training/record_presentation.py"
CSS = ROOT / "frontend/src/styles/training.css"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_page() -> None:
    text = PAGE.read_text(encoding="utf-8")
    if "TrainingRequirementList" in text:
        return

    text = replace_once(
        text,
        'import PersonnelLicencePanel from "../components/training/PersonnelLicencePanel";\n',
        'import PersonnelLicencePanel from "../components/training/PersonnelLicencePanel";\nimport TrainingRequirementList from "../components/training/TrainingRequirementList";\n',
        "requirement component import",
    )
    text = replace_once(
        text,
        'import { saveDownloadedFile } from "../utils/downloads";\n',
        'import { saveDownloadedFile } from "../utils/downloads";\nimport { canonicalTrainingType, complianceStatusLabel, completedEventStatusWithoutRequirement, explicitTrainingRequirementKey } from "../utils/trainingPresentation";\n',
        "presentation helpers import",
    )

    phase_pattern = re.compile(
        r'function coursePhase\(course: TrainingCourseRead \| null \| undefined\): "INITIAL" \| "REFRESHER" \| "ONE_OFF" \| "UNKNOWN" \{.*?\n\}\n\nfunction courseFamilyKey\(course: TrainingCourseRead \| null \| undefined\): string \{.*?\n\}\n',
        re.S,
    )
    phase_replacement = '''function coursePhase(course: TrainingCourseRead | null | undefined): "INITIAL" | "RECURRENT" | "ONE_OFF" | "UNKNOWN" {
  if (!course) return "UNKNOWN";
  const canonical = canonicalTrainingType(course);
  if (canonical) return canonical;
  const status = String(course.status || "").trim().toUpperCase();
  if (status === "ONE_OFF" || status === "ONE-OFF" || status === "ONE OFF") return "ONE_OFF";
  return "UNKNOWN";
}

function courseFamilyKey(course: TrainingCourseRead | null | undefined): string {
  return explicitTrainingRequirementKey(course);
}
'''
    text, count = phase_pattern.subn(phase_replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"course classification block: expected one match, found {count}")

    status_record_pattern = re.compile(
        r'function effectiveTrainingStatusForRecord\(record: TrainingRecordRead \| null \| undefined, item: TrainingStatusItem \| null \| undefined\): string \{.*?\n\}\n\nfunction normaliseRecordLifecycleStatus',
        re.S,
    )
    status_record_replacement = '''function effectiveTrainingStatusForRecord(record: TrainingRecordRead | null | undefined, item: TrainingStatusItem | null | undefined): string {
  if (item) return effectiveTrainingStatus(item);
  return completedEventStatusWithoutRequirement(Boolean(record?.completion_date));
}

function normaliseRecordLifecycleStatus'''
    text, count = status_record_pattern.subn(status_record_replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"record status block: expected one match, found {count}")

    status_label_pattern = re.compile(r'function statusLabel\(status: string\): string \{.*?\n\}\n\nfunction statusPillClass', re.S)
    text, count = status_label_pattern.subn(
        'function statusLabel(status: string): string {\n  return complianceStatusLabel(status);\n}\n\nfunction statusPillClass',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"status label block: expected one match, found {count}")

    text = text.replace('coursePhase(course) !== "REFRESHER"', 'coursePhase(course) !== "RECURRENT"')
    text = text.replace('label: "Due soon"', 'label: "Due Soon"')
    text = text.replace('label: "Not done"', 'label: "Not completed"')
    text = text.replace('<strong>Next due</strong>', '<strong>Next Due</strong>')
    text = text.replace('>Next due</button>', '>Next Due</button>')
    text = text.replace('<th>Last done</th>', '<th>Last Completed</th>')
    text = text.replace('<th>Due</th>', '<th>Next Due</th>')
    text = text.replace('<th>Next event</th>', '<th>Scheduled</th>')
    text = text.replace('Completed log', 'Training requirements')
    text = text.replace('{viewMode === "completed" ? "Training record log" : "Missing required courses"}', '{viewMode === "completed" ? "Training requirements" : "Missing required courses"}')
    text = text.replace(
        '"Completed records and current due status are shown together here. This is the main working view for the individual profile."',
        '"Applicable requirements are shown once with Last Completed, Next Due, Scheduled, compliance and evidence. Historical completions remain in each requirement disclosure."',
    )

    table_pattern = re.compile(
        r'\{viewMode === "completed" \? \(\s*<table className="table table-striped table-compact training-history-table training-history-table--banded training-history-table--responsive">.*?</table>\s*\) : \(\s*(<table className="table table-striped table-compact training-history-table training-history-table--banded training-history-table--responsive">)',
        re.S,
    )
    replacement = '''{viewMode === "completed" ? (
                      <TrainingRequirementList
                        items={items}
                        courses={courses}
                        records={records}
                        files={files}
                        canEdit={canEdit}
                        onEditRecord={openRecordEditor}
                        onDeleteRecord={(record) => void deleteRecord(record)}
                        onOpenEvidence={(file) => void openFileViewer(file)}
                        onUploadEvidence={triggerInlineAttachmentUpload}
                        onRecordCompletion={(coursePk) => beginNewRecord(coursePk)}
                      />
                    ) : (
                      \\1'''
    text, count = table_pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"primary training table: expected one match, found {count}")

    PAGE.write_text(text, encoding="utf-8")


def patch_backend() -> None:
    text = BACKEND.read_text(encoding="utf-8")
    if "_group_pdf_status_items" not in text:
        marker = "\ndef _compact_pdf_builder(original_builder, *args, **kwargs) -> bytes:\n"
        helper = '''
def _group_pdf_status_items(status_items: list[Any], course_by_id: dict[str, Any]) -> list[Any]:
    courses = list(course_by_id.values())
    grouped: dict[str, tuple[Any, Any]] = {}
    for item in status_items:
        code = str(getattr(item, "course_id", "") or "")
        course = next((candidate for candidate in courses if str(getattr(candidate, "course_id", "")) == code or str(getattr(candidate, "id", "")) == code), None)
        key = explicit_recurrence_key(course, courses) if course is not None else f"item:{code}"
        current = grouped.get(key)
        current_course = current[1] if current else None
        candidate_rank = 2 if course is not None and is_recurrent_course_explicit(course) else 1 if course is not None and is_initial_course_explicit(course) else 0
        current_rank = 2 if current_course is not None and is_recurrent_course_explicit(current_course) else 1 if current_course is not None and is_initial_course_explicit(current_course) else 0
        if current is None or candidate_rank > current_rank:
            grouped[key] = (item, course)
    return [entry[0] for entry in grouped.values()]

'''
        if marker not in text:
            raise RuntimeError("PDF builder marker missing")
        text = text.replace(marker, helper + marker, 1)

    anchor = '        report_settings = kwargs.get("report_settings") or {}\n'
    if 'status_items = _group_pdf_status_items(status_items, course_by_id)' not in text:
        text = replace_once(text, anchor, anchor + '        status_items = _group_pdf_status_items(status_items, course_by_id)\n', "PDF requirement grouping")

    old_sort = 'group_records.sort(key=lambda record: (record.completion_date or date.min, record.created_at or datetime.min), reverse=True)'
    if old_sort in text:
        text = text.replace(old_sort, 'group_records.sort(key=lambda record: (record.completion_date or date.min, str(record.created_at or "")), reverse=True)', 1)

    old_contacts = 'tenant.setdefault("contact_email", mask_public_email(getattr(user.amo, "contact_email", None) if getattr(user, "amo", None) else None))\n    tenant.setdefault("contact_phone", mask_public_phone(getattr(user.amo, "contact_phone", None) if getattr(user, "amo", None) else None))'
    new_contacts = 'tenant.setdefault("contact_email", getattr(user.amo, "contact_email", None) if getattr(user, "amo", None) else None)\n    tenant.setdefault("contact_phone", getattr(user.amo, "contact_phone", None) if getattr(user, "amo", None) else None)'
    if old_contacts in text:
        text = text.replace(old_contacts, new_contacts, 1)

    anchor_rows = '    rows = _build_requirement_rows(db, amo_id=amo_id, user=user)\n'
    filter_rows = '''    rows = _build_requirement_rows(db, amo_id=amo_id, user=user)
    if record_id:
        rows = [
            row for row in rows
            if any(str(history.get("record_id")) == str(record_id) for history in row.get("history") or [])
        ]
'''
    if 'if record_id:\n        rows = [' not in text:
        text = replace_once(text, anchor_rows, filter_rows, "record grant scoping")

    BACKEND.write_text(text, encoding="utf-8")


def patch_css() -> None:
    text = CSS.read_text(encoding="utf-8")
    old = '''  .training-history-table--responsive {
    min-width: 620px;
  }
}'''
    new = '''  .training-history-table--responsive {
    min-width: 0;
    table-layout: auto;
  }

  .training-history-table--responsive thead th,
  .training-history-table--responsive tbody td {
    width: auto !important;
    min-width: 0 !important;
    overflow-wrap: anywhere;
  }

  .training-table-wrap {
    overflow-x: visible;
  }
}'''
    if old in text:
        text = text.replace(old, new, 1)
    CSS.write_text(text, encoding="utf-8")


def main() -> None:
    patch_page()
    patch_backend()
    patch_css()


if __name__ == "__main__":
    main()
