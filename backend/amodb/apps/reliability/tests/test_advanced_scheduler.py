from __future__ import annotations

from amodb.apps.reliability import advanced_scheduler as scheduler


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return self._rows


class _Session:
    bind = None

    def __init__(self, source_tenants):
        self._source_tenants = source_tenants
        self._query_count = 0
        self.rollback_count = 0

    def query(self, *_args, **_kwargs):
        self._query_count += 1
        if self._query_count == 1:
            return _Query(self._source_tenants)
        return _Query([])

    def rollback(self):
        self.rollback_count += 1


def test_scheduled_cycle_propagates_recorded_accountable_actor(monkeypatch):
    db = _Session([("AMO-1",)])
    calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(scheduler, "WriteSessionLocal", lambda: db)
    monkeypatch.setattr(scheduler, "close_session_safely", lambda _db: None)
    monkeypatch.setattr(
        scheduler,
        "_accountable_actor_id",
        lambda _db, *, amo_id: "USER-1" if amo_id == "AMO-1" else None,
    )
    monkeypatch.setattr(
        scheduler.services,
        "harvest_internal_sources",
        lambda _db, *, amo_id, actor_user_id: (
            calls.append(("harvest", amo_id, actor_user_id)) or [object()]
        ),
    )
    monkeypatch.setattr(
        scheduler.services,
        "run_due_metrics",
        lambda _db, *, amo_id, actor_user_id: (
            calls.append(("metrics", amo_id, actor_user_id)) or [object(), object()]
        ),
    )

    result = scheduler.run_reliability_cycle()

    assert result == {
        "tenants": 1,
        "harvested_batches": 1,
        "calculation_runs": 2,
    }
    assert calls == [
        ("harvest", "AMO-1", "USER-1"),
        ("metrics", "AMO-1", "USER-1"),
    ]
    assert db.rollback_count == 0


def test_scheduled_cycle_skips_harvest_cleanly_without_owner(monkeypatch):
    db = _Session([("AMO-2",)])
    metric_actors: list[str | None] = []

    monkeypatch.setattr(scheduler, "WriteSessionLocal", lambda: db)
    monkeypatch.setattr(scheduler, "close_session_safely", lambda _db: None)
    monkeypatch.setattr(scheduler, "_accountable_actor_id", lambda _db, *, amo_id: None)

    def _unexpected_harvest(*_args, **_kwargs):
        raise AssertionError("Internal harvesting must not run without an accountable owner")

    monkeypatch.setattr(scheduler.services, "harvest_internal_sources", _unexpected_harvest)
    monkeypatch.setattr(
        scheduler.services,
        "run_due_metrics",
        lambda _db, *, amo_id, actor_user_id: (
            metric_actors.append(actor_user_id) or []
        ),
    )

    result = scheduler.run_reliability_cycle()

    assert result == {
        "tenants": 1,
        "harvested_batches": 0,
        "calculation_runs": 0,
    }
    assert metric_actors == [None]
    assert db.rollback_count == 0
