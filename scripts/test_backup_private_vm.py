import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("backup_test", Path(__file__).with_name("backup_private_vm.py"))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_current_dump_is_accepted():
    backup.validate_backup_timestamp(99_000, now=100_000)


def test_copying_an_old_dump_does_not_make_it_fresh():
    with pytest.raises(RuntimeError, match="stale"):
        backup.validate_backup_timestamp(100_000 - 13 * 3600, now=100_000)


def test_future_source_clock_is_reported():
    with pytest.raises(RuntimeError, match="clock"):
        backup.validate_backup_timestamp(101_000, now=100_000)


@pytest.mark.parametrize("age", [0, -1, float("nan"), float("inf")])
def test_invalid_freshness_configuration_is_rejected(age):
    with pytest.raises(ValueError):
        backup.validate_backup_timestamp(99_000, now=100_000, max_age_hours=age)


def test_failed_transfer_removes_its_partial_copy(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["backup", "--destination", str(tmp_path / "copies")])
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda _: SimpleNamespace(free=2 * 1024**3))
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ssh")
    monkeypatch.setattr(backup.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        backup.main()
    assert not list((tmp_path / "copies").iterdir())
