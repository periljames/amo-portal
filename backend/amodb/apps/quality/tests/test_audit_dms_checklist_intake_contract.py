from __future__ import annotations

import inspect
from types import SimpleNamespace

import amodb.apps.quality.audit_checklist_template_router as checklist_router

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


def test_pending_checklists_have_progress_but_cannot_be_selected(monkeypatch):
    document = SimpleNamespace(id="doc-1", code="CHK-1", title="Checklist", manual_type="CHECKLIST")
    hidden = SimpleNamespace(id="hidden", code="HIDDEN", title="Restricted", manual_type="CHECKLIST")
    workflow = SimpleNamespace(manual_id=document.id, id="wf-1", revision_id="rev-1", state="TECHNICAL_REVIEW", updated_at=None)
    class Query:
        def __init__(self, rows): self.rows = rows
        def filter(self, *args): return self
        def order_by(self, *args): return self
        def limit(self, *args): return self
        def all(self): return self.rows
        def first(self): return self.rows[0] if self.rows else None
    class DB:
        def query(self, entity):
            if entity is checklist_router.manual_models.Manual: return Query([document, hidden])
            if entity is checklist_router.doc_control_models.DocumentWorkflowInstance: return Query([workflow])
            if entity is checklist_router.doc_control_models.DocumentControlProfile: return Query([SimpleNamespace(manual_id="hidden")])
            return Query([])
    monkeypatch.setattr(checklist_router, "set_postgres_tenant_context", lambda *a, **kw: None)
    monkeypatch.setattr(checklist_router, "_audit", lambda *a, **kw: SimpleNamespace())
    monkeypatch.setattr(checklist_router, "_manual_tenant", lambda *a: SimpleNamespace(id="tenant-1", slug="dms"))
    monkeypatch.setattr(checklist_router, "_active_user", lambda *a: SimpleNamespace())
    monkeypatch.setattr(checklist_router, "can_read_manual", lambda user, profile: profile is None)
    monkeypatch.setattr(checklist_router, "_current_effective_revision", lambda *a: None)
    monkeypatch.setattr(checklist_router, "_audit_context", lambda *a: ("context", "INTERNAL", "QUALITY", "auditee"))
    result = checklist_router.list_current_dms_checklists(
        audit_id="audit-1", q=None, document_type="CHECKLIST",
        ctx=SimpleNamespace(amo_id="amo-1", user_id="user-1"), db=DB(),
    )
    assert result["items"] == []
    assert len(result["pending"]) == 1
    assert result["pending"][0]["state"] == "TECHNICAL_REVIEW"
    assert "workflow=wf-1" in result["pending"][0]["review_url"]
