from __future__ import annotations

import os


def pytest_runtest_logreport(report) -> None:
    """Expose pytest failures as GitHub Actions annotations.

    GitHub's check-run API retains annotations even when raw job logs are not
    available to API consumers. Keep this hook side-effect free with respect to
    test execution; it only mirrors failures already reported by pytest.
    """
    if not report.failed or os.getenv("GITHUB_ACTIONS") != "true":
        return

    path, line, _ = report.location
    message = str(report.longrepr).replace("\r", " ").replace("\n", "%0A")
    message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(
        f"::error file={path},line={line + 1},title=Reliability pytest failure::"
        f"{report.nodeid}%0A{message}"
    )
