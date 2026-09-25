from types import SimpleNamespace
from unittest.mock import Mock

from amodb.apps.doc_control import reminder_service as reminders
from amodb.apps.platform import ops_gateway as gateway


def test_reminder_disconnect_closes_session_and_retries_without_rollback(monkeypatch):
    stop = Mock()
    stop.is_set.side_effect = [False, True]
    db = Mock()
    db.rollback.side_effect = RuntimeError("connection already closed")
    close = Mock()
    cycle = Mock(side_effect=RuntimeError("server closed the connection unexpectedly"))
    monkeypatch.setattr(reminders, "_stop_event", stop)
    monkeypatch.setattr(reminders, "probe_database", lambda: True)
    monkeypatch.setattr(reminders, "WriteSessionLocal", lambda: db)
    monkeypatch.setattr(reminders, "close_session_safely", close)
    monkeypatch.setattr(reminders, "run_document_control_reminder_cycle", cycle)
    reminders._scheduler_loop()
    close.assert_called_once_with(db)
    db.rollback.assert_not_called()
    assert stop.wait.call_args.args[0] < reminders.REMINDER_INTERVAL_SECONDS


def test_reminder_skips_work_during_outage(monkeypatch):
    stop = Mock()
    stop.is_set.side_effect = [False, True]
    session = Mock()
    monkeypatch.setattr(reminders, "_stop_event", stop)
    monkeypatch.setattr(reminders, "probe_database", lambda: False)
    monkeypatch.setattr(reminders, "WriteSessionLocal", session)
    reminders._scheduler_loop()
    session.assert_not_called()
    stop.wait.assert_called_once()


def test_snapshot_freshness_expires_and_recovers(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(gateway, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    store = gateway.SnapshotStore()
    assert not store.status()["fresh"]
    for mode in ("REAL", "DEMO"):
        store.set(mode, {"generated_at": "original"})
    assert store.status()["fresh"]
    store.error(RuntimeError("unavailable"))
    assert not store.status()["fresh"]
    assert store.get("REAL")["freshness"]["stale"]
    clock[0] += gateway.REFRESH_SECONDS * 3 + 1
    store.set("REAL", {})
    assert not store.status()["fresh"]  # DEMO is still stale.
    store.set("DEMO", {})
    assert store.status()["fresh"]


def test_snapshot_cleanup_disconnect_does_not_escape(monkeypatch):
    db = Mock()
    db.close.side_effect = RuntimeError("connection already closed")
    monkeypatch.setattr(gateway, "ReadSessionLocal", lambda: db)
    monkeypatch.setattr(gateway, "build_snapshot", Mock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(gateway, "snapshot_store", gateway.SnapshotStore())
    gateway.refresh_snapshots_once()
    db.invalidate.assert_called_once()
    assert not gateway.snapshot_store.status()["fresh"]


def test_readiness_returns_503_for_stale_snapshot(monkeypatch):
    from amodb import platform_ops_main as ops
    monkeypatch.setattr(ops.broker, "health", lambda: {"running": True, "snapshot_fresh": True})
    monkeypatch.setattr(ops.snapshot_store, "status", lambda: {"fresh": False, "modes": ["REAL", "DEMO"]})
    monkeypatch.setattr(ops.app.state, "snapshot_task", SimpleNamespace(done=lambda: False), raising=False)
    assert ops.readyz().status_code == 503
    monkeypatch.setattr(ops.snapshot_store, "status", lambda: {"fresh": True})
    assert ops.readyz().status_code == 200
    monkeypatch.setattr(ops.broker, "health", lambda: {"running": True, "snapshot_fresh": False})
    assert ops.readyz().status_code == 503
