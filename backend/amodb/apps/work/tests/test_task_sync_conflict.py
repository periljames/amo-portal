from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from amodb.apps.work import router, schemas


def test_task_conflict_is_locked_and_can_be_reviewed_before_reapply(monkeypatch):
    current = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    class Query:
        locked = False
        def filter(self, *args):
            return self
        def with_for_update(self):
            self.locked = True
            return self
        def first(self):
            assert self.locked, "Concurrent device updates must lock before checking the revision"
            return SimpleNamespace(updated_at=current)
    monkeypatch.setattr(router.command_service, "begin_command", lambda *a, **kw: SimpleNamespace(replayed=False))
    payload = schemas.TaskCardUpdate(last_known_updated_at=datetime(2026, 10, 15, 12, tzinfo=timezone.utc))
    db = SimpleNamespace(query=lambda *args: Query())
    user = SimpleNamespace(id="user", effective_amo_id="amo", role="PLANNING_ENGINEER")
    with pytest.raises(HTTPException) as failure:
        router.update_task(1, payload, "device-task-key", db, user)
    assert failure.value.status_code == 409
    assert failure.value.detail["error_code"] == "TASK_REVISION_CONFLICT"
    assert failure.value.detail["retryable"] is True
    assert failure.value.detail["current_updated_at"] == current.isoformat()
