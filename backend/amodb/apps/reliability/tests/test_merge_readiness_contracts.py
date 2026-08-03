from __future__ import annotations

import inspect
from types import SimpleNamespace

from amodb.apps.accounts.models import AccountRole
from amodb.apps.reliability import advanced_scheduler, router, services


class _QueryRecorder:
    def __init__(self) -> None:
        self.limit_value: int | None = None
        self.offset_value: int | None = None

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, value: int):
        self.offset_value = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def all(self):
        return []


class _QueryDB:
    def __init__(self) -> None:
        self.query_recorder = _QueryRecorder()

    def query(self, *_args):
        return self.query_recorder


class _FakeThread:
    def __init__(self) -> None:
        self.started = 0
        self.joined = 0
        self.alive = False

    def start(self) -> None:
        self.started += 1
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: int | None = None) -> None:
        assert timeout == 5
        self.joined += 1
        self.alive = False


def test_event_queries_are_bounded_even_for_direct_service_callers():
    db = _QueryDB()
    services.list_reliability_events(
        db,
        amo_id="amo-1",
        limit=100_000,
        offset=-10,
    )
    assert db.query_recorder.limit_value == 200
    assert db.query_recorder.offset_value == 0


def test_ehm_pagination_is_bounded_and_normalized():
    assert router._normalize_ehm_pagination(10_000, -25) == (router.MAX_EHM_PAGE_SIZE, 0)
    assert router._normalize_ehm_pagination(0, 12) == (100, 12)


def test_scheduler_start_is_idempotent_and_stop_joins(monkeypatch):
    fake_thread = _FakeThread()
    constructed = 0

    def build_thread(**kwargs):
        nonlocal constructed
        constructed += 1
        assert kwargs["daemon"] is True
        assert kwargs["name"] == "reliability-scheduler"
        return fake_thread

    monkeypatch.setattr(advanced_scheduler, "_thread", None)
    monkeypatch.setattr(advanced_scheduler, "_enabled", lambda: True)
    monkeypatch.setattr(advanced_scheduler.threading, "Thread", build_thread)

    advanced_scheduler.start_reliability_scheduler()
    advanced_scheduler.start_reliability_scheduler()

    assert constructed == 1
    assert fake_thread.started == 1
    assert advanced_scheduler._thread is fake_thread

    advanced_scheduler.stop_reliability_scheduler()
    assert fake_thread.joined == 1
    assert advanced_scheduler._thread is None
    assert advanced_scheduler._stop_event.is_set()


def test_disabled_scheduler_does_not_create_worker(monkeypatch):
    monkeypatch.setattr(advanced_scheduler, "_thread", None)
    monkeypatch.setattr(advanced_scheduler, "_enabled", lambda: False)

    def forbidden_thread(**_kwargs):
        raise AssertionError("Disabled scheduler must not construct a thread")

    monkeypatch.setattr(advanced_scheduler.threading, "Thread", forbidden_thread)
    advanced_scheduler.start_reliability_scheduler()
    assert advanced_scheduler._thread is None


def test_fracas_evidence_export_is_tenant_scoped_and_audited():
    source = inspect.getsource(router.export_fracas_evidence_pack)
    assert "FRACASCase.amo_id == _amo_id(current_user)" in source
    assert "FRACASCase.id == fracas_case_id" in source
    assert "actor_user_id=current_user.id" in source
    assert "correlation_id=generate_uuid7()" in source
    assert "amo_id=_amo_id(current_user)" in source


def test_fracas_evidence_export_is_restricted_to_authorized_participants():
    case = SimpleNamespace(
        created_by_user_id="creator",
        updated_by_user_id="owner",
        verified_by_user_id="verifier",
        approved_by_user_id="approver",
    )
    participant = SimpleNamespace(id="owner", role=AccountRole.TECHNICIAN)
    outsider = SimpleNamespace(id="outsider", role=AccountRole.TECHNICIAN)
    quality_manager = SimpleNamespace(id="quality", role=AccountRole.QUALITY_MANAGER)

    assert router._can_export_fracas(participant, case) is True
    assert router._can_export_fracas(quality_manager, case) is True
    assert router._can_export_fracas(outsider, case) is False
