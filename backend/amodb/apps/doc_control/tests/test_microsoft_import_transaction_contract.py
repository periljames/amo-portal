"""Microsoft Graph import keeps DOCX draft and SharePoint provenance atomic.

Network and file extraction are isolated; the production FastAPI handler, its
call into the canonical DOCX intake service and the DB commit order are exercised.
These tests do not claim live Entra/Graph or object-store acceptance.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.params import Depends

from amodb.apps.doc_control import microsoft_router as bridge
from amodb.apps.manuals import core_router as manuals


class _Query:
    def filter(self, *_args):
        return self

    def first(self):
        return None


class _DB:
    def __init__(self, link):
        self.link = link
        self.commits = 0

    def query(self, *_args):
        return _Query()

    def commit(self):
        assert self.link.last_imported_revision_id == "revision-02"
        assert self.link.last_imported_etag == "version-02"
        assert self.link.last_imported_source_sha256 == hashlib.sha256(b"PK\\x03\\x04test").hexdigest()
        self.commits += 1


def _prepare(monkeypatch, *, item_etags=("version-02", "version-02"), imported_etag=None):
    link = SimpleNamespace(
        tenant_id="tenant-one", manual_id="manual-one",
        drive_id="drive-one", item_id="item-one",
        last_imported_etag=imported_etag, last_imported_revision_id=None,
    )
    db = _DB(link)
    tenant = SimpleNamespace(amo_id="tenant-one", slug="tenant")
    manual = SimpleNamespace(
        id="manual-one", code="QMS-MAN", title="QMS manual",
        manual_type="GENERAL", owner_role="Quality",
    )
    accesses = []
    etags = iter(item_etags)
    monkeypatch.setattr(bridge, "require_control_user", lambda _u: None)
    monkeypatch.setattr(bridge, "resolve_tenant", lambda *_args: tenant)
    monkeypatch.setattr(bridge, "get_manual", lambda *_args: manual)
    monkeypatch.setattr(bridge, "_link", lambda *_args, **kwargs: accesses.append(kwargs.get("lock")) or link)
    monkeypatch.setattr(bridge, "_connected", lambda *_args: object())

    def current(*_args):
        return {"id": "item-one", "name": "manual.docx", "eTag": next(etags)}
    monkeypatch.setattr(bridge, "current_item", current)
    monkeypatch.setattr(bridge, "download_docx", lambda *_args, **_kwargs: b"PK\\x03\\x04test")
    monkeypatch.setattr(bridge.manual_core, "_validate_docx_upload", lambda *_args: None)
    monkeypatch.setattr(bridge.manual_core, "_extract_docx_content", lambda *_args: {
        "metadata": {"part_number": "QMS-MAN", "revision_number": "02"},
    })
    monkeypatch.setattr(bridge, "update_link", lambda row, item: setattr(row, "observed_etag", item["eTag"]))
    monkeypatch.setattr(bridge, "link_payload", lambda _row: {"linked": True})
    monkeypatch.setattr(bridge, "audit", lambda *_args, **_kwargs: None)
    return db, accesses


def _invoke(db, background):
    return asyncio.run(bridge.import_document(
        tenant_slug="tenant", manual_id="manual-one",
        payload=bridge.ImportDocument(revision_number="02", expected_etag="version-02"),
        request=Request({"type": "http", "path": "/test", "method": "POST", "headers": []}),
        background_tasks=background,
        db=db, user=SimpleNamespace(id="user-one"),
    ))


def test_http_docx_upload_always_commits_but_internal_adapter_can_defer():
    policy = inspect.signature(manuals.upload_docx_revision).parameters["commit_changes"].default
    assert isinstance(policy, Depends)
    assert policy.dependency is manuals._http_docx_upload_commits
    assert policy.dependency() is True


def test_graph_import_holds_lock_until_source_provenance_is_committed(monkeypatch):
    db, accesses = _prepare(monkeypatch)
    calls = []

    async def upload(**kwargs):
        calls.append(kwargs.get("commit_changes"))
        assert db.commits == 0
        assert kwargs["rev_number"] == "02"
        return {
            "manual_id": "manual-one", "revision_id": "revision-02",
            "status": "DRAFT", "source_sha256": hashlib.sha256(b"PK\\x03\\x04test").hexdigest(),
        }

    monkeypatch.setattr(bridge.manual_core, "upload_docx_revision", upload)
    background = BackgroundTasks()
    outcome = _invoke(db, background)
    assert accesses == [True]
    assert calls == [False], "Canonical DOCX intake must not commit and release the SharePoint lock"
    assert db.commits == 1, "Import source provenance and canonical revision must commit together"
    assert outcome["revision_id"] == "revision-02"
    assert len(background.tasks) == 2


def test_graph_import_rejects_repeated_etag_before_creating_another_draft(monkeypatch):
    db, accesses = _prepare(monkeypatch, imported_etag="version-02")

    async def forbidden_upload(**_kwargs):
        raise AssertionError("Repeated Graph version cannot create another draft")

    monkeypatch.setattr(bridge.manual_core, "upload_docx_revision", forbidden_upload)
    with pytest.raises(HTTPException) as failure:
        _invoke(db, BackgroundTasks())
    assert failure.value.status_code == 409
    assert accesses == [True]
    assert db.commits == 0


def test_graph_import_rejects_mid_download_source_change(monkeypatch):
    db, _accesses = _prepare(monkeypatch, item_etags=("version-02", "version-03"))

    async def forbidden_upload(**_kwargs):
        raise AssertionError("A newer source eTag must not enter canonical DMS intake")

    monkeypatch.setattr(bridge.manual_core, "upload_docx_revision", forbidden_upload)
    with pytest.raises(HTTPException) as failure:
        _invoke(db, BackgroundTasks())
    assert failure.value.status_code == 409
    assert db.commits == 0
