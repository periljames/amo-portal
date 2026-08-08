from __future__ import annotations

import os


_FAILURES: list[tuple[str, str, int, str]] = []


def pytest_runtest_logreport(report) -> None:
    """Collect failures without altering pytest execution or outcomes."""
    if not report.failed or os.getenv("GITHUB_ACTIONS") != "true":
        return

    path, line, _ = report.location
    _FAILURES.append((report.nodeid, path, line + 1, str(report.longrepr)))


def _escape_workflow_command(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def pytest_sessionfinish(session, exitstatus) -> None:
    """Expose collected failures after pytest capture has finished.

    Writing directly to stdout at session shutdown lets GitHub Actions retain
    the exact failing node and traceback as check-run annotations while keeping
    the suite's exit status unchanged.
    """
    if os.getenv("GITHUB_ACTIONS") != "true":
        return

    for nodeid, path, line, longrepr in _FAILURES:
        detail = f"{nodeid}\n{longrepr}"
        annotation = (
            f"::error file={path},line={line},title=Reliability pytest failure::"
            f"{_escape_workflow_command(detail)}\n"
        )
        os.write(1, annotation.encode("utf-8", errors="replace"))
