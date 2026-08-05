from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


frontend_path = Path("frontend/src/components/training/TrainingWorkbookImportDialog.tsx")
frontend = frontend_path.read_text(encoding="utf-8")
frontend = replace_once(
    frontend,
    '                type="file"\n                accept=',
    '                type="file"\n                aria-label="Training workbook file"\n                accept=',
    "file input label",
)
frontend = replace_once(
    frontend,
    '<section className={`training-import-status training-import-status--${statusTone(job.status)}`}>',
    '<section className={`training-import-status training-import-status--${statusTone(job.status)}`} aria-live="polite" aria-atomic="true">',
    "status live region",
)
frontend = replace_once(
    frontend,
    '<div className="training-import-alert training-import-alert--danger">\n                <AlertTriangle size={18} />\n                <span>The reviewed commit failed and can be retried.',
    '<div className="training-import-alert training-import-alert--danger" role="alert">\n                <AlertTriangle size={18} />\n                <span>The reviewed commit failed and can be retried.',
    "retry failure alert",
)
frontend = replace_once(
    frontend,
    '<label><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, staff code or issue" /></label>',
    '<label><Search size={16} /><input aria-label="Search workbook review rows" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, staff code or issue" /></label>',
    "review search label",
)
frontend = replace_once(
    frontend,
    '                            <select\n                              value={decisions[row.id] || ""}',
    '                            <select\n                              aria-label={`Decision for ${row.display_label || row.source_key || `row ${row.source_row}`}`}\n                              value={decisions[row.id] || ""}',
    "decision select label",
)
frontend = replace_once(
    frontend,
    '{error ? <div className="training-import-alert training-import-alert--danger"><XCircle size={18} /><span>{error}</span></div> : null}',
    '{error ? <div className="training-import-alert training-import-alert--danger" role="alert"><XCircle size={18} /><span>{error}</span></div> : null}',
    "generic error alert",
)
frontend_path.write_text(frontend, encoding="utf-8")


test_path = Path("backend/amodb/apps/training/tests/test_workbook_import_mapping.py")
tests = test_path.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    "from datetime import date\n",
    "from datetime import date\nfrom inspect import getsource\nfrom io import BytesIO\nfrom zipfile import ZIP_DEFLATED, ZipFile\n\nimport pytest\nfrom fastapi import HTTPException\n",
    "test imports",
)
tests = replace_once(
    tests,
    "    _person_payload,\n    _workbook_params,\n)",
    "    _person_payload,\n    _upsert_person,\n    _workbook_params,\n)",
    "upsert import",
)
tests += '''


def test_imported_accounts_remain_least_privilege_and_existing_authorization_is_not_mutated():
    source = getsource(_upsert_person)
    assert source.count("role=account_models.AccountRole.TECHNICIAN") == 2
    assert "user.department_id =" not in source
    assert "raise PersonnelIdentityChanged(row.id" in source


def test_workbook_archive_validation_rejects_non_excel_payloads():
    from amodb.apps.training.workbook_router import _validate_workbook_archive

    with pytest.raises(HTTPException) as error:
        _validate_workbook_archive(b"not-an-excel-archive")
    assert error.value.status_code == 400


def test_workbook_archive_validation_accepts_bounded_office_archive():
    from amodb.apps.training.workbook_router import _validate_workbook_archive

    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
    _validate_workbook_archive(payload.getvalue())
'''
test_path.write_text(tests, encoding="utf-8")


doc_path = Path("docs/training/TRAINING_TRACKER_WORKBOOK_MAPPING.md")
doc = doc_path.read_text(encoding="utf-8")
marker = "- Derived workbook sheets are represented by live portal capabilities rather than duplicated stored calculations.\n"
addition = '''- Commit requests lock and claim one durable import job, preventing duplicate concurrent workers.
- Decisions are accepted only for rows explicitly marked for review and only from the server-provided option set.
- Workbook archives are bounded by both compressed and expanded size and must be readable, unencrypted Office archives.
- Workbook imports never grant privileged account roles or change an existing user's authorization department.
- Commit-time identity changes return the affected People row to review; they do not convert a reviewed action into another access action.
- Final partial batches publish progress and observe cancellation before the importer moves to the next dependency stage.
- An operational commit cannot complete unless its database audit event is created.
'''
doc = replace_once(doc, marker, marker + addition, "hardening documentation")
doc_path.write_text(doc, encoding="utf-8")
