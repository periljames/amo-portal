"""Development browser/backend realtime configuration must agree."""
import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def runtime():
    spec = importlib.util.spec_from_file_location("portal_dev_runtime_test", Path(__file__).with_name("dev_runtime.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backend,explicit,expected", [
    ("true", None, "1"), ("false", None, "0"),
    ("true", "0", "0"), ("false", "1", "1"),
])
def test_runtime_aligns_browser_realtime_without_overriding_explicit_choice(runtime, tmp_path, monkeypatch, backend, explicit, expected):
    monkeypatch.delenv("VITE_REALTIME_ENABLED", raising=False)
    env_file = tmp_path / ".env.development"
    env_file.write_text(
        "SECRET_KEY=test-only\nREFRESH_TOKEN_PEPPER=test-only\n"
        "DATABASE_WRITE_URL=postgresql://test-only\n"
        f"REALTIME_ENABLED={backend}\n"
        + (f"VITE_REALTIME_ENABLED={explicit}\n" if explicit is not None else ""),
    )
    assert runtime._load_environment(env_file)["VITE_REALTIME_ENABLED"] == expected
