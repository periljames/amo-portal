from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from amodb.apps.doc_control.knowledge_path_integrity import (
    _compose_node_path,
    _ensure_documentation_node_path_before_insert,
)


def test_compose_node_path_is_stable_for_root_and_child() -> None:
    root_id = "12345678-0000-4000-8000-000000000001"
    root_path, root_depth = _compose_node_path(
        parent_path=None,
        parent_depth=None,
        node_id=root_id,
        code="DOC ROOT",
    )
    assert root_path == "/doc-root~12345678"
    assert root_depth == 0

    child_path, child_depth = _compose_node_path(
        parent_path=root_path,
        parent_depth=root_depth,
        node_id="abcdef12-0000-4000-8000-000000000002",
        code="SYS / Quality",
    )
    assert child_path == "/doc-root~12345678/sys-quality~abcdef12"
    assert child_depth == 1


def test_before_insert_populates_required_root_path_before_sql() -> None:
    target = SimpleNamespace(
        id=None,
        tenant_id="tenant-1",
        parent_id=None,
        code="DOC-ROOT",
        path=None,
        depth=None,
    )

    _ensure_documentation_node_path_before_insert(None, None, target)

    uuid.UUID(target.id)
    assert target.path == f"/doc-root~{target.id[:8]}"
    assert target.depth == 0


def test_before_insert_uses_persisted_parent_path_for_child() -> None:
    class Result:
        @staticmethod
        def one_or_none():
            return ("/doc-root~12345678", 0)

    class Connection:
        @staticmethod
        def execute(_statement):
            return Result()

    target = SimpleNamespace(
        id="abcdef12-0000-4000-8000-000000000002",
        tenant_id="tenant-1",
        parent_id="parent-1",
        code="SYS-QUALITY",
        path=None,
        depth=None,
    )

    _ensure_documentation_node_path_before_insert(None, Connection(), target)

    assert target.path == "/doc-root~12345678/sys-quality~abcdef12"
    assert target.depth == 1


def test_before_insert_fails_closed_when_parent_path_is_missing() -> None:
    class Result:
        @staticmethod
        def one_or_none():
            return None

    class Connection:
        @staticmethod
        def execute(_statement):
            return Result()

    target = SimpleNamespace(
        id="abcdef12-0000-4000-8000-000000000002",
        tenant_id="tenant-1",
        parent_id="missing-parent",
        code="SYS-QUALITY",
        path=None,
        depth=None,
    )

    with pytest.raises(ValueError, match="parent must exist"):
        _ensure_documentation_node_path_before_insert(None, Connection(), target)
