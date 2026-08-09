from __future__ import annotations

from types import SimpleNamespace

import pytest

from amodb.apps.platform import platform_command_queue, services


class _FakeDB:
    def __init__(self, platform_job=None):
        self.platform_job = platform_job
        self.flushed = 0

    def get(self, model, key):
        if self.platform_job is not None and str(getattr(self.platform_job, "id", "")) == str(key):
            return self.platform_job
        return None

    def flush(self):
        self.flushed += 1


def _job(**overrides):
    values = {
        "id": "command-1",
        "command_name": "RUN_PLATFORM_HEALTH_PROBE",
        "status": "QUEUED",
        "tenant_id": None,
        "actor_user_id": "requester-a",
        "requested_by_user_id": "requester-a",
        "approved_by_user_id": None,
        "output_json": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _queue_job(command_job_id: str = "command-1"):
    return SimpleNamespace(
        payload_json={"command_job_id": command_job_id, "actor_id": "requester-a"},
        max_attempts=1,
        attempt_count=1,
    )


def test_execution_blocks_missing_second_person_approval(monkeypatch):
    job = _job(command_name="TENANT_DEACTIVATE", approved_by_user_id=None)
    db = _FakeDB(job)
    events = []
    monkeypatch.setattr(services, "add_job_event", lambda _db, _job, status, message, data=None: events.append((status, message)))

    with pytest.raises(PermissionError):
        platform_command_queue.process_leased_job(db, _queue_job())

    assert job.status == "NEEDS_APPROVAL"
    assert db.flushed == 1
    assert events and events[-1][0] == "NEEDS_APPROVAL"


def test_execution_blocks_self_approval(monkeypatch):
    job = _job(
        command_name="TENANT_DEACTIVATE",
        approved_by_user_id="requester-a",
    )
    db = _FakeDB(job)
    monkeypatch.setattr(services, "add_job_event", lambda *_args, **_kwargs: None)

    with pytest.raises(PermissionError):
        platform_command_queue.process_leased_job(db, _queue_job())

    assert job.status == "NEEDS_APPROVAL"


def test_distinct_approver_allows_leased_execution(monkeypatch):
    job = _job(
        command_name="TENANT_DEACTIVATE",
        approved_by_user_id="approver-b",
    )
    db = _FakeDB(job)
    called = []

    def _process(_db, queue_job):
        called.append(queue_job)
        return {"command_job_id": job.id, "status": "SUCCEEDED"}

    monkeypatch.setattr(services, "process_command_queue_job", _process)
    result = platform_command_queue.process_leased_job(db, _queue_job())

    assert result["status"] == "SUCCEEDED"
    assert called


def test_execute_command_job_is_queue_only(monkeypatch):
    job = _job(status="PENDING")
    called = []

    def _queue(_db, queued_job, *, actor_id):
        called.append((queued_job, actor_id))

    monkeypatch.setattr(services, "queue_command_job", _queue)
    services.execute_command_job(SimpleNamespace(), job, actor_id="requester-a")

    assert called == [(job, "requester-a")]
