"""Inspect registered API routes without starting services or connecting to live data."""
import json
import os
import sys
from pathlib import Path

# Inspection uses the same isolated schema configuration as the test harness.
os.environ.update({
    "APP_ENV": "test", "ALLOW_SQLITE_FOR_TESTS": "1", "AMODB_SKIP_MODEL_IMPORTS": "1",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:", "DATABASE_WRITE_URL": "sqlite+pysqlite:///:memory:",
    "SECRET_KEY": "offline-route-inspection-only",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amodb.apps.accounts import models  # noqa: E402,F401 - match test harness model bootstrap
from amodb.main import app  # noqa: E402

routes = []
for route in app.routes:
    endpoint = getattr(route, "endpoint", None)
    owner = getattr(endpoint, "__module__", "")
    module = owner.split(".apps.")[-1].split(".")[0] if ".apps." in owner else "portal"
    for method in sorted(getattr(route, "methods", set()) & {"POST", "PUT", "PATCH", "DELETE"}):
        routes.append({"module": module, "method": method, "path": route.path,
                       "offline_create_path": getattr(endpoint, "offline_command_path", None)})
Path(sys.argv[1]).write_text(json.dumps(routes, indent=2), encoding="utf-8")
