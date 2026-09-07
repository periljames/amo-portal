from __future__ import annotations

import inspect

from amodb.apps.quality.audit_checklist_template_router import (
    bind_current_dms_checklist,
    upload_dms_checklist_from_audit,
)


def test_qms_upload_registers_a_dms_draft_without_bypassing_document_control() -> None:
    source = inspect.getsource(upload_dms_checklist_from_audit)

    assert "manual_core.upload_pdf_revision" in source
    assert "manual_core.upload_docx_revision" in source
    assert '"binding": None' in source
    assert "_instantiate_binding(" not in source
    assert "_issued_template_for_document(" not in source


def test_only_the_current_effective_dms_revision_is_bound_to_fieldwork() -> None:
    source = inspect.getsource(bind_current_dms_checklist)

    assert "_current_effective_revision(db, document)" in source
    assert "Complete Document Control approval first" in source
    assert "_issued_template_for_document(" in source
    assert "_instantiate_binding(" in source
