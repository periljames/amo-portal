from __future__ import annotations

import ast
import json
import py_compile
import re
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"


def _read(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"Required release file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        target = child.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            parts = [target.attr]
            value = target.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            names.add(".".join(reversed(parts)))
    return names


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"Function {name} was not found")


def _assert_before(text: str, needles: tuple[str, ...], boundary: str) -> None:
    boundary_index = text.index(boundary)
    for needle in needles:
        assert text.index(needle) < boundary_index, f"{needle} must run before {boundary}"


def main() -> int:
    checks: dict[str, dict[str, Any]] = {}

    package_path = BACKEND_ROOT / "amodb/apps/platform/__init__.py"
    package_text = _read(package_path)
    policy_calls = (
        "install_tenant_provider_override_policy()",
        "install_fiscalization_enqueue_policy()",
        "install_tenant_admin_links()",
    )
    _assert_before(package_text, policy_calls, "from .saas_router import")
    checks["platform-policy-install-order"] = {"passed": True, "calls": policy_calls}

    admin_links_path = BACKEND_ROOT / "amodb/apps/platform/saas_admin_links.py"
    admin_links_text = _read(admin_links_path)
    tenant_route = "/maintenance/{amoCode}/admin/email-settings"
    assert tenant_route in admin_links_text
    assert "module._setup_links = setup_links" in admin_links_text
    frontend_router = _read(FRONTEND_ROOT / "src/router.tsx")
    registered_route = tenant_route.replace("{amoCode}", ":amoCode")
    assert registered_route in frontend_router, registered_route
    checks["tenant-admin-link-is-registered"] = {
        "passed": True,
        "backend": tenant_route,
        "frontend": registered_route,
    }

    fiscal_path = BACKEND_ROOT / "amodb/apps/platform/saas_fiscalization_policy.py"
    fiscal_text = _read(fiscal_path)
    for token in (
        "FISCALIZED",
        "RECONCILIATION_REQUIRED",
        "SUBMITTING",
        "SUBMITTED",
        "FAILED",
        "validate_fiscalization_enqueue",
        "saas_services.enqueue_fiscalization = guarded_enqueue_fiscalization",
    ):
        assert token in fiscal_text, token
    checks["terminal-fiscalization-policy"] = {"passed": True}

    gateway_path = BACKEND_ROOT / "amodb/apps/realtime/gateway.py"
    gateway_text = _read(gateway_path)
    gateway_tree = ast.parse(gateway_text, filename=str(gateway_path))
    on_connect = _function(gateway_tree, "_on_connect")
    on_connect_calls = _call_names(on_connect)
    assert not any(name.endswith("flush_pending") for name in on_connect_calls), on_connect_calls
    assert any(name.endswith("_drain_wakeup.set") for name in on_connect_calls), on_connect_calls
    assert gateway_text.index("result.wait_for_publish(timeout=timeout)") < gateway_text.index(
        "row.published_at = datetime.now(timezone.utc)"
    )
    checks["mqtt-callback-and-puback-safety"] = {
        "passed": True,
        "on_connect_calls": sorted(on_connect_calls),
    }

    cleanup_test = BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_release_cleanup.py"
    cleanup_test_text = _read(cleanup_test)
    for token in (
        "test_platform_package_installs_runtime_admin_and_fiscalization_policies",
        "test_terminal_or_uncertain_fiscalization_state_cannot_be_reset",
        "test_mqtt_connect_callback_only_wakes_background_drain",
    ):
        assert token in cleanup_test_text, token
    checks["release-regressions"] = {"passed": True}

    retry_path = ROOT / ".github/scripts/retry_transient.py"
    rerun_path = ROOT / ".github/scripts/rerun_failed_pr_checks.py"
    retry_text = _read(retry_path)
    rerun_text = _read(rerun_path)
    assert "TRANSIENT_PATTERNS" in retry_text
    assert "output did not match a transient" in retry_text
    assert "rerun-failed-jobs" in rerun_text
    assert "current_pr_head" in rerun_text
    assert "refusing to re-run stale checks" in rerun_text
    checks["ci-retry-safety"] = {"passed": True}

    workflow_paths = (
        ROOT / ".github/workflows/saas-control-plane-ci.yml",
        ROOT / ".github/workflows/quality-module-ci.yml",
        ROOT / ".github/workflows/workforce-postgres-hotfix.yml",
        ROOT / ".github/workflows/duty-rostering-ci.yml",
    )
    workflow_rows: list[dict[str, Any]] = []
    for path in workflow_paths:
        text = _read(path)
        assert ".github/scripts/retry_transient.py" in text, path
        assert not re.search(r"(?m)^\s*- run: pip install -r requirements\.txt\s*$", text), path
        assert not re.search(r"(?m)^\s*- run: npm ci\s*$", text), path
        workflow_rows.append({"path": str(path.relative_to(ROOT)), "passed": True})
    checks["workflow-transient-install-guards"] = {
        "passed": True,
        "workflows": workflow_rows,
    }

    recheck_workflow = _read(ROOT / ".github/workflows/recheck-transient-ci.yml")
    for token in (
        "actions: write",
        "rerun_failed_pr_checks.py",
        "inputs.pr_number",
    ):
        assert token in recheck_workflow, token
    checks["manual-exact-head-recheck"] = {"passed": True}

    compile_targets = (
        admin_links_path,
        fiscal_path,
        gateway_path,
        cleanup_test,
        retry_path,
        rerun_path,
        Path(__file__),
    )
    for path in compile_targets:
        py_compile.compile(str(path), doraise=True)
    checks["python-compile"] = {
        "passed": True,
        "files": [str(path.relative_to(ROOT)) for path in compile_targets],
    }

    print(json.dumps({"passed": True, "checks": checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
