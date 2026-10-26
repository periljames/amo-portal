import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock


def test_worker_waits_during_outage_and_resumes_without_losing_queue(monkeypatch, caplog):
    path = Path(__file__).parents[1] / "backend/amodb/apps/doc_control/evidence_pack_worker_main.py"
    spec = importlib.util.spec_from_file_location("evidence_worker_recovery_test", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    waits = []
    stop_state = {"stop": False}
    event = SimpleNamespace(is_set=lambda: stop_state["stop"], set=lambda: stop_state.update(stop=True), wait=lambda delay: waits.append(delay))
    processor = Mock(side_effect=lambda: event.set() or True)
    probe = Mock(side_effect=[False, False, True])
    dispose = Mock()
    storage = SimpleNamespace(validate_storage_configuration=Mock())
    amodb = ModuleType("amodb")
    amodb.storage = storage
    monkeypatch.setitem(sys.modules, "amodb", amodb)
    monkeypatch.setitem(sys.modules, "amodb.apps.doc_control.evidence_pack_job_service", SimpleNamespace(process_one_pending_job=processor))
    monkeypatch.setitem(sys.modules, "amodb.database", SimpleNamespace(dispose_engines=dispose, probe_database=probe))
    monkeypatch.setitem(sys.modules, "amodb.database_resilience", SimpleNamespace(database_circuit=SimpleNamespace(retry_after_seconds=lambda: 8)))
    monkeypatch.setattr(worker, "threading", SimpleNamespace(Event=lambda: event))
    monkeypatch.setattr(worker, "signal", SimpleNamespace(SIGINT=2, SIGTERM=15, signal=Mock()))
    monkeypatch.setattr(worker, "_configure_worker_pool", lambda: None)
    monkeypatch.setattr(worker, "_load_env_file", lambda path: None)
    monkeypatch.setattr(sys, "argv", ["worker", "--poll-seconds", "0.5"])
    worker.main()
    assert waits == [8, 8]
    assert probe.call_count == 3
    processor.assert_called_once()
    dispose.assert_called_once()
    assert sum("worker paused" in record.message for record in caplog.records) == 1
