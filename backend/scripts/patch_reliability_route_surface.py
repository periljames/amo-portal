from __future__ import annotations

import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "frontend/src/app/PortalRouteSurface.tsx"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    text = text.replace(
        'const ReliabilityReportsPage = lazy(() => import("../pages/ReliabilityReportsPage"));\n',
        "",
        1,
    )
    text = text.replace('  "reliability",\n', "", 1)
    pattern = re.compile(
        r'\n  if \(module === "reliability" && view === "reports" && parts\.length === 4\) \{.*?\n  \}\n',
        re.DOTALL,
    )
    text, count = pattern.subn("\n", text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected one legacy Reliability report interception, found {count}.")
    if "ReliabilityReportsPage" in text:
        raise RuntimeError("Legacy Reliability report page remains in PortalRouteSurface.")
    PATH.write_text(text, encoding="utf-8")
    print("PortalRouteSurface now delegates every Reliability route to the canonical wildcard workspace.")


if __name__ == "__main__":
    main()
