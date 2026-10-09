from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

import amodb.apps.quality.audit_checklist_template_router as checklist_router

from amodb.apps.quality.audit_checklist_template_router import (
    bind_current_dms_checklist,
    get_checklist_binding,
    list_checklist_bindings,
    upload_dms_checklist_from_audit,
)


def test_empty_issued_checklist_cannot_create_a_misleading_binding():
    with pytest.raises(HTTPException, match="no questions") as error:
        checklist_router._instantiate_binding(
            None, ctx=None, audit=None, template=None,
            revision=SimpleNamespace(items=[]), reason="Selected for audit", allow_existing_items=False,
        )
    assert error.value.status_code == 409


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


def test_dms_bind_returns_201_only_after_committed_binding_is_read_back() -> None:
    source = inspect.getsource(bind_current_dms_checklist)

    commit_index = source.index("db.commit()")
    verification_index = source.index("persisted = db.query(QualityAuditChecklistBinding)")
    return_index = source.index("return _binding_dict(persisted)")

    assert commit_index < verification_index < return_index
    assert "CHECKLIST_BINDING_COMMIT_NOT_VISIBLE" in source
    assert "set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)" in source



def test_checklist_binding_authority_is_paginated_with_an_authoritative_total(monkeypatch) -> None:
    audit_id = uuid.uuid4()
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            audit_id=audit_id,
            template_id=f"template-{index}",
            template_revision_id=f"revision-{index}",
            template_code=f"CHK-{index:03d}",
            revision_no=1,
            content_sha256=f"sha-{index}",
            item_snapshot=[],
            source_references=[],
            instantiated_item_ids=[],
            application_reason="Regression fixture",
            applied_by_user_id="quality-user",
            applied_at=None,
        )
        for index in range(101)
    ]

    class Query:
        def __init__(self, values):
            self.values = list(values)

        def filter(self, *args):
            return self

        def count(self):
            return len(self.values)

        def order_by(self, *args):
            self.values = list(reversed(self.values))
            return self

        def offset(self, count):
            self.values = self.values[count:]
            return self

        def limit(self, count):
            self.values = self.values[:count]
            return self

        def all(self):
            return self.values

        def first(self):
            return self.values[0] if self.values else None

    class DB:
        def query(self, entity):
            assert entity is checklist_router.QualityAuditChecklistBinding
            return Query(rows)

    monkeypatch.setattr(checklist_router, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(checklist_router, "_audit", lambda *args, **kwargs: SimpleNamespace(id=audit_id))

    result = list_checklist_bindings(
        audit_id=audit_id,
        offset=0,
        limit=100,
        ctx=SimpleNamespace(amo_id="amo-1", user_id="quality-user"),
        db=DB(),
    )

    assert result["total"] == 101
    assert len(result["items"]) == 100
    assert result["items"][0]["id"] == str(rows[-1].id)


def test_checklist_binding_can_be_confirmed_directly_by_id(monkeypatch) -> None:
    audit_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    row = SimpleNamespace(
        id=binding_id,
        audit_id=audit_id,
        template_id="template-1",
        template_revision_id="revision-1",
        template_code="CHK-001",
        revision_no=1,
        content_sha256="sha-1",
        item_snapshot=[],
        source_references=[],
        instantiated_item_ids=[],
        application_reason="Regression fixture",
        applied_by_user_id="quality-user",
        applied_at=None,
    )

    class Query:
        def filter(self, *args):
            return self

        def first(self):
            return row

    class DB:
        def query(self, entity):
            assert entity is checklist_router.QualityAuditChecklistBinding
            return Query()

    monkeypatch.setattr(checklist_router, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(checklist_router, "_audit", lambda *args, **kwargs: SimpleNamespace(id=audit_id))

    result = get_checklist_binding(
        audit_id=audit_id,
        binding_id=binding_id,
        ctx=SimpleNamespace(amo_id="amo-1", user_id="quality-user"),
        db=DB(),
    )

    assert result["id"] == str(binding_id)


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


def test_reselecting_current_dms_checklist_returns_saved_binding_without_duplicate_rows(monkeypatch):
    document = SimpleNamespace(id="doc-1")
    revision = SimpleNamespace(id="revision-1")
    existing = SimpleNamespace(id="binding-1")
    audit = SimpleNamespace(id="audit-1")

    class Query:
        def __init__(self, row): self.row = row
        def filter(self, *args): return self
        def first(self): return self.row

    class DB:
        def query(self, entity):
            if entity is checklist_router.manual_models.Manual: return Query(document)
            if entity is checklist_router.QualityAuditChecklistBinding: return Query(existing)
            return Query(None)

    monkeypatch.setattr(checklist_router, "assert_quality_permission", lambda *a: None)
    monkeypatch.setattr(checklist_router, "set_postgres_tenant_context", lambda *a, **kw: None)
    monkeypatch.setattr(checklist_router, "_audit", lambda *a, **kw: audit)
    monkeypatch.setattr(checklist_router, "_assert_checklist_can_change", lambda *a: None)
    monkeypatch.setattr(checklist_router, "_manual_tenant", lambda *a: SimpleNamespace(id="tenant-1"))
    monkeypatch.setattr(checklist_router, "_active_user", lambda *a: SimpleNamespace())
    monkeypatch.setattr(checklist_router, "can_read_manual", lambda *a: True)
    monkeypatch.setattr(checklist_router, "_document_type", lambda *a: "CHECKLIST")
    monkeypatch.setattr(checklist_router, "_current_effective_revision", lambda *a: revision)
    monkeypatch.setattr(checklist_router, "_issued_template_for_document", lambda *a, **kw: (SimpleNamespace(), revision))
    monkeypatch.setattr(checklist_router, "_binding_dict", lambda row: {"id": row.id})

    def duplicate(*a, **kw):
        raise AssertionError("A retry must not create checklist rows or increment usage")

    monkeypatch.setattr(checklist_router, "_instantiate_binding", duplicate)
    for _ in range(2):
        result = bind_current_dms_checklist(
            audit_id=audit.id, document_id=document.id,
            payload=checklist_router.CurrentDocumentChecklistBindingCreate(
                reason="Selected for audit", allow_existing_items=False,
                response_type="YES_NO_NA", response_options=[],
            ),
            ctx=SimpleNamespace(amo_id="amo-1", user_id="user-1"), db=DB(),
        )
        assert result == {"id": "binding-1"}
