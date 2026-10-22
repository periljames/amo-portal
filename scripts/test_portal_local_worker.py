import importlib.util
from pathlib import Path

def test_local_worker_keeps_all_selected_families_without_spawning_processes(monkeypatch):
    path = Path(__file__).parents[1] / "backend/amodb/jobs/portal_worker_main.py"
    spec = importlib.util.spec_from_file_location("local_worker_test", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    families = set(worker.DEFAULT_FAMILIES.split(","))
    assert len(families) == 7
    captured = []
    monkeypatch.setattr(worker, "_available", lambda: families)
    monkeypatch.setattr(worker, "_child_main", lambda selected: captured.append(selected))
    monkeypatch.setattr(worker.multiprocessing, "get_context", lambda *_: (_ for _ in ()).throw(AssertionError("local worker must not spawn")))
    monkeypatch.setattr("sys.argv", ["worker", "--single-process"])
    monkeypatch.delenv("PORTAL_ENV_FILE", raising=False)
    monkeypatch.delenv("PORTAL_WORKER_FAMILIES", raising=False)
    worker.main()
    assert captured == [families]
