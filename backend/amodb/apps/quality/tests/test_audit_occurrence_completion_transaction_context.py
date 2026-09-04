from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.quality import audit_occurrence_completion_router
from amodb.apps.quality.tenant_security import (
    _TENANT_CONTEXT_KEY,
    _restore_postgres_tenant_context,
)


@pytest.mark.parametrize(
    "handler",
    [
        audit_occurrence_completion_router.create_governed_document_request,
        audit_occurrence_completion_router.update_governed_document_request,
        audit_occurrence_completion_router.create_audit_meeting,
        audit_occurrence_completion_router.update_audit_meeting,
        audit_occurrence_completion_router.update_closing_narrative,
    ],
)
def test_post_commit_reads_restore_transaction_local_tenant_context(handler) -> None:
    """FORCE RLS hides committed rows until the request tenant GUC is rebound."""
    source = inspect.getsource(handler)

    commit_index = source.rindex("db.commit()")
    context_index = source.rindex("set_postgres_tenant_context(")
    refresh_index = source.index("db.refresh(", commit_index)

    assert commit_index < context_index < refresh_index


def test_shared_quality_context_is_restored_when_post_commit_transaction_begins():
    session = SimpleNamespace(info={_TENANT_CONTEXT_KEY: ("amo-1", "user-1")})
    connection = MagicMock()
    connection.dialect.name = "postgresql"

    _restore_postgres_tenant_context(session, None, connection)

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    parameters = [call.args[1] for call in connection.execute.call_args_list]
    assert statements == [
        "SELECT set_config('app.tenant_id', :amo_id, true)",
        "SELECT set_config('app.user_id', :user_id, true)",
    ]
    assert parameters == [{"amo_id": "amo-1"}, {"user_id": "user-1"}]


def test_shared_quality_context_does_not_write_postgres_settings_on_other_dialects():
    session = SimpleNamespace(info={_TENANT_CONTEXT_KEY: ("amo-1", "user-1")})
    connection = MagicMock()
    connection.dialect.name = "sqlite"

    _restore_postgres_tenant_context(session, None, connection)

    connection.execute.assert_not_called()


def test_opening_and_closing_meeting_creation_is_retry_safe():
    source = inspect.getsource(audit_occurrence_completion_router.create_audit_meeting)

    assert 'payload.meeting_type in {"OPENING", "CLOSING"}' in source
    assert "QualityAuditMeeting.meeting_type == payload.meeting_type" in source
    assert 'QualityAuditMeeting.status != "CANCELLED"' in source
    assert "with_for_update().first()" in source


def test_meeting_lists_preserve_history_but_expose_one_current_singleton():
    earlier = datetime(2026, 9, 3, 8, tzinfo=timezone.utc)
    later = datetime(2026, 9, 3, 9, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(id="opening-old", meeting_type="OPENING", status="PLANNED", scheduled_start=earlier, created_at=earlier, updated_at=earlier),
        SimpleNamespace(id="opening-new", meeting_type="OPENING", status="PLANNED", scheduled_start=earlier, created_at=later, updated_at=later),
        SimpleNamespace(id="closing-cancelled", meeting_type="CLOSING", status="CANCELLED", scheduled_start=later, created_at=later, updated_at=later),
        SimpleNamespace(id="follow-up", meeting_type="FOLLOW_UP", status="PLANNED", scheduled_start=later, created_at=later, updated_at=later),
    ]

    current = audit_occurrence_completion_router._current_meeting_rows(rows)

    assert [row.id for row in current] == ["opening-new", "follow-up"]

