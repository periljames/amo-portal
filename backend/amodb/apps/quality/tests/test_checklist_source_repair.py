from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality import audit_checklist_template_router as router
from amodb.apps.quality.tests.test_audit_checklist_upload_parser import _paper_form


def test_source_scheme_cannot_silently_invent_response_columns():
    with pytest.raises(HTTPException) as missing_scheme:
        router._issued_template_for_document(None, ctx=None, audit=None, document=None, revision=None,
            items_override=[{"prompt": "Question with no declared source columns", "response_options": []}],
            response_type_override="SOURCE")
    assert missing_scheme.value.status_code == 422


@pytest.mark.parametrize("suffix,method,endpoint", [
    ("source-review", "GET", "review_checklist_source"),
    ("rebuild-source", "POST", "rebuild_checklist_from_source"),
])
def test_source_repair_routes_precede_dynamic_audit_dispatch(suffix, method, endpoint):
    from amodb.apps.quality.canonical_router import router as canonical
    from starlette.routing import Match
    path = f"/api/maintenance/safarilink/quality/audits/{uuid.uuid4()}/checklist-bindings/{suffix}"
    scope = {"type": "http", "path": path, "method": method, "root_path": ""}
    match = next(route for route in canonical.routes if route.matches(scope)[0] == Match.FULL)
    assert match.endpoint.__name__ == endpoint


def test_dms_binding_reads_original_table_instead_of_indexed_text(tmp_path):
    source = tmp_path / "checklist.docx"
    data = _paper_form()
    source.write_bytes(data)
    revision = SimpleNamespace(source_storage_path=str(source), source_filename=source.name,
        source_sha256=hashlib.sha256(data).hexdigest(), rev_number="01")
    # No database query is needed to turn a controlled source into questions.
    items = router._checklist_items_from_revision(None, document=SimpleNamespace(code="QMS-20"), revision=revision)
    assert len(items) == 3
    assert items[0]["prompt"] == "Is there a description and organogram?"
    revision.source_sha256 = "0" * 64
    with pytest.raises(HTTPException) as mismatch:
        router._checklist_items_from_revision(None, document=SimpleNamespace(code="QMS-20"), revision=revision)
    assert mismatch.value.status_code == 409
    source.unlink()
    with pytest.raises(HTTPException) as missing:
        router._checklist_items_from_revision(None, document=SimpleNamespace(code="QMS-20"), revision=revision)
    assert missing.value.status_code == 409


def test_source_preview_is_stable_but_detects_changed_questions_and_binding():
    binding = SimpleNamespace(id="binding", instantiated_item_ids=["1", "2"], content_sha256="old")
    document = SimpleNamespace(code="QMS-20")
    revision = SimpleNamespace(id="revision", source_filename="source.docx")
    def token(prompt="Source question", item_id=None):
        return router._source_preview([(binding, document, revision,
            [{"item_id": item_id or str(uuid.uuid4()), "prompt": prompt, "sort_order": 10}])])[1]
    original = token()
    assert token() == original
    assert token("Changed question") != original
    binding.content_sha256 = "changed"
    assert token() != original


@pytest.mark.parametrize("recorded", ["response_status", "objective_evidence", "finding_id", "completed_at", "governance", "receipt", "evidence", None])
def test_rebuild_blocks_every_kind_of_recorded_fieldwork(recorded):
    row = SimpleNamespace(response_status="PENDING", objective_evidence=None, finding_id=None, completed_at=None)
    if recorded in vars(row):
        setattr(row, recorded, "COMPLIANT" if recorded == "response_status" else "recorded")
    class Query:
        def __init__(self, found): self.found = found
        def filter(self, *args): return self
        def all(self): return [row]
        def first(self): return self.found
    class DB:
        def query(self, model):
            key = {"QualityAuditChecklistExecutionGovernance": "governance",
                   "QualityAuditFieldworkMutationReceipt": "receipt", "QualityAuditEvidenceArtifact": "evidence"}.get(model.__name__)
            return Query(object() if key and key == recorded else None)
    blocker = router._checklist_rebuild_blocker(DB(), amo_id="amo", audit_id=uuid.uuid4())
    assert bool(blocker) == (recorded is not None)


@pytest.mark.parametrize("mode", ["clean", "stale", "answered"])
def test_source_rebuild_transaction_preserves_history_and_rejects_stale_or_answered(db_session, monkeypatch, mode):
    from amodb.database import Base
    from amodb.apps.audit.models import AuditEvent
    from amodb.apps.quality.audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance, QualityAuditFieldworkMutationReceipt
    from amodb.apps.quality.audit_evidence_models import QualityAuditEvidenceArtifact
    from amodb.apps.quality.audit_preparation_models import QualityAuditPreparationRevision, QualityAuditPreparationEvent
    from amodb.apps.quality import audit_preparation_router as preparation_router

    db = db_session
    Base.metadata.create_all(db.get_bind(), tables=[model.__table__ for model in (
        router.models.QualityAuditChecklistItem, router.QualityAuditChecklistTemplate,
        router.QualityAuditChecklistTemplateRevision, router.QualityAuditChecklistBinding,
        router.QualityAuditChecklistMemory, QualityAuditChecklistExecutionGovernance,
        QualityAuditFieldworkMutationReceipt, QualityAuditEvidenceArtifact,
        QualityAuditPreparationRevision, QualityAuditPreparationEvent,
    )])
    ctx = SimpleNamespace(amo_id="amo", user_id="auditor")
    audit = router.models.QMSAudit(amo_id=ctx.amo_id, domain="AMO", audit_ref="QAR-TEST", title="Source repair")
    db.add(audit)
    db.flush()
    document = SimpleNamespace(id="doc", code="QMS-20", title="Checklist", manual_type="CHECKLIST")
    source = SimpleNamespace(id="rev", source_filename="source.docx")
    reference = {"source_system": "DOCUMENT_CONTROL", "document_id": "doc", "revision_id": "rev"}
    template = router.QualityAuditChecklistTemplate(amo_id=ctx.amo_id, template_code="QMS-20", title="Checklist", canonical_document_id="doc")
    db.add(template)
    db.flush()
    old = router.QualityAuditChecklistTemplateRevision(amo_id=ctx.amo_id, template_id=template.id, revision_no=1,
        status="ISSUED", items=[{"prompt": "Date of Audit:"}, {"prompt": "Source question"}],
        source_references=[reference], content_sha256="0" * 64, change_reason="Legacy import")
    db.add(old)
    db.flush()
    binding = router._instantiate_binding(db, ctx=ctx, audit=audit, template=template, revision=old,
        reason="Original import", allow_existing_items=False)
    db.flush()
    old_ids = list(binding.instantiated_item_ids)
    previous = QualityAuditPreparationRevision(amo_id=ctx.amo_id, audit_id=audit.id, revision_no=1,
        status="ISSUED", checklist_snapshot=[{"prompt": "Date of Audit:"}], source_fingerprint="0" * 64,
        change_reason="Issued original preparation")
    db.add(previous)
    db.commit()
    parsed = [router.ChecklistTemplateItem(prompt="Source question", section="Operations", sort_order=1).model_dump()]
    plans = [(binding, document, source, parsed)]
    token = router._source_preview(plans)[1]
    monkeypatch.setattr(router, "assert_quality_permission", lambda *args: None)
    monkeypatch.setattr(router, "set_postgres_tenant_context", lambda *args, **kw: None)
    monkeypatch.setattr(router, "_source_rebuild_plan", lambda *args, **kw: plans)
    monkeypatch.setattr(router, "_source_reference", lambda *args: reference)
    # The transaction still captures the actual rebuilt live rows; unrelated
    # preparation reference retrieval is exercised by its own routing tests.
    monkeypatch.setattr(preparation_router, "_capture_sources", lambda *args, **kw: {
        "audit_snapshot": {}, "checklist_snapshot": [{"prompt": row.prompt} for row in db.query(router.models.QualityAuditChecklistItem).all()],
        "document_request_snapshot": [], "source_references": [], "source_fingerprint": "1" * 64,
    })
    if mode == "answered":
        db.query(router.models.QualityAuditChecklistItem).first().response_status = "COMPLIANT"
        db.commit()
    payload = router.ChecklistSourceRebuild(preview_sha256="f" * 64 if mode == "stale" else token, reason="Repair original table import")
    if mode != "clean":
        with pytest.raises(HTTPException) as blocked:
            router.rebuild_checklist_from_source(audit.id, payload, ctx, db)
        assert blocked.value.status_code == 409
        assert db.query(router.models.QualityAuditChecklistItem).count() == 2
        assert db.query(router.QualityAuditChecklistBinding).count() == 1
        assert db.query(QualityAuditPreparationRevision).count() == 1
        return
    result = router.rebuild_checklist_from_source(audit.id, payload, ctx, db)
    assert result["question_count"] == 1
    assert result["requires_preparation_issue"] is True
    assert db.query(router.models.QualityAuditChecklistItem).one().prompt == "Source question"
    assert str(db.query(router.models.QualityAuditChecklistItem).one().id) not in old_ids
    assert db.query(router.QualityAuditChecklistTemplateRevision).count() == 2
    assert previous.status == "ISSUED"
    assert previous.checklist_snapshot == [{"prompt": "Date of Audit:"}]
    latest = db.query(QualityAuditPreparationRevision).order_by(QualityAuditPreparationRevision.revision_no.desc()).first()
    assert latest.status == "DRAFT" and latest.supersedes_revision_id == previous.id
    assert latest.checklist_snapshot == [{"prompt": "Source question"}]
    event = db.query(AuditEvent).filter(AuditEvent.action == "CHECKLIST_SOURCE_REBUILT").one()
    assert event.before["bindings"][0]["instantiated_item_ids"] == old_ids
    assert event.after["bindings"][0]["instantiated_item_ids"] != old_ids
