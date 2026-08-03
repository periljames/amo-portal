from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def remove_tracked_runtime_artifacts() -> None:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    artifacts = [
        path
        for path in completed.stdout.splitlines()
        if "/__pycache__/" in f"/{path}"
        or path.endswith(".pyc")
        or path.endswith("reliability_v2_test.db")
    ]
    if artifacts:
        subprocess.run(
            ["git", "rm", "-f", "--ignore-unmatch", *artifacts],
            cwd=ROOT,
            check=True,
        )


def main() -> None:
    replace_once(
        ROOT / "backend/amodb/apps/reliability/tests/test_router.py",
        '        amo_id="amo-1",\n',
        '        amo_id=str(amo.id),\n',
        "tenant-aware trend test identifier",
    )
    replace_once(
        ROOT / "frontend/scripts/complete-reliability-workspace.mjs",
        "workspace = workspace.replace('function routeState(pathname: string): RouteState {', 'export function routeState(pathname: string): RouteState {');\n",
        "",
        "Fast Refresh route-state export",
    )

    finalizer = ROOT / "backend/scripts/finalize_reliability_migration.py"
    finalizer_text = finalizer.read_text(encoding="utf-8")
    for role_id in (
        "rel-role-viewer",
        "rel-role-engineer",
        "rel-role-manager",
        "rel-role-authority",
    ):
        old = f"u.amo_id || ':' || u.id || ':{role_id}'"
        new = f"u.amo_id || '|' || u.id || '|{role_id}'"
        if old not in finalizer_text:
            raise RuntimeError(f"Missing authorization identifier anchor for {role_id}")
        finalizer_text = finalizer_text.replace(old, new, 1)
    finalizer.write_text(finalizer_text, encoding="utf-8")

    diagnostic = ROOT / "backend/scripts/run_reliability_completion_diagnostic.py"
    if diagnostic.exists():
        replace_once(
            diagnostic,
            '    stages.append("model_defaults")\n\n    stage("frontend_service",',
            '    stages.append("model_defaults")\n    stage("autogenerate_isolation", "python backend/scripts/isolate_reliability_autogenerate.py")\n\n    stage("frontend_service",',
            "Reliability diagnostic metadata isolation stage",
        )

    remove_tracked_runtime_artifacts()
    print("Reliability completion blockers corrected.")


if __name__ == "__main__":
    main()
