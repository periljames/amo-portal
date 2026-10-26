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


@pytest.mark.parametrize("mode", ["dev", "preview"])
def test_shared_frontend_mode_keeps_topology_and_uses_selected_server(runtime, monkeypatch, mode):
    monkeypatch.setattr(runtime, "_npm_executable", lambda: "npm")
    services = runtime._services({}, include_frontend=True, reload=False, frontend_mode=mode)
    frontend = next(service for service in services if service.name == "frontend")
    assert frontend.port == 5173
    assert frontend.command[:3] == ["npm", "run", mode]
    assert "--strictPort" in frontend.command
    assert any(service.port == 8080 for service in services)


def test_windows_background_jobs_yield_to_interactive_services(runtime, monkeypatch):
    from types import SimpleNamespace
    if runtime.os.name != "nt":
        pytest.skip("Windows process priority policy")
    calls = []
    def popen(command, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(pid=99, stdout=None)
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)
    runtime._spawn(runtime.Service("api", ["python"], Path.cwd()), {})
    runtime._spawn(runtime.Service("jobs", ["python"], Path.cwd()), {})
    assert calls[0]["creationflags"] & runtime.subprocess.CREATE_NEW_PROCESS_GROUP
    assert not calls[0]["creationflags"] & runtime.subprocess.BELOW_NORMAL_PRIORITY_CLASS
    assert calls[1]["creationflags"] & runtime.subprocess.BELOW_NORMAL_PRIORITY_CLASS
