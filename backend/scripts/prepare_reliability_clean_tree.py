from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def replace_reliability_navigation() -> None:
    path = ROOT / "frontend/src/app/portalRouteManifest.ts"
    text = path.read_text(encoding="utf-8")
    start_marker = '  if (department === "reliability") {'
    end_marker = '  if (department === "safety")'
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    replacement = '''  if (department === "reliability") {
    return {
      id: "department-reliability",
      label: "Reliability",
      icon: "reliability",
      path: `${base}/reliability`,
      children: [
        {
          id: "reliability-command",
          label: "Command",
          path: `${base}/reliability`,
          children: [
            { id: "reliability-workbench", label: "Workbench", path: `${base}/reliability`, exact: true },
            { id: "reliability-events", label: "Occurrences", path: `${base}/reliability/events` },
            { id: "reliability-alerts", label: "Alerts", path: `${base}/reliability/alerts` },
            { id: "reliability-fracas", label: "FRACAS", path: `${base}/reliability/cases` },
            { id: "reliability-sources", label: "Source Control", path: `${base}/reliability/sources` },
            { id: "reliability-ingestion", label: "Ingestion Batches", path: `${base}/reliability/ingestion` },
          ],
        },
        {
          id: "reliability-analysis",
          label: "Analysis",
          path: `${base}/reliability/fleet`,
          children: [
            { id: "reliability-fleet", label: "Fleet", path: `${base}/reliability/fleet` },
            { id: "reliability-systems", label: "ATA Systems", path: `${base}/reliability/systems` },
            { id: "reliability-components", label: "Components", path: `${base}/reliability/components` },
            { id: "reliability-engines", label: "Engine Trends", path: `${base}/reliability/engines` },
            { id: "reliability-calculations", label: "KPI Calculations", path: `${base}/reliability/calculations` },
            { id: "ehm-dashboard", label: "EHM Dashboard", path: `${base}/ehm/dashboard` },
            { id: "ehm-trends", label: "EHM Trends", path: `${base}/ehm/trends` },
            { id: "ehm-uploads", label: "EHM Uploads", path: `${base}/ehm/uploads` },
          ],
        },
        {
          id: "reliability-governance",
          label: "Governance",
          path: `${base}/reliability/program`,
          children: [
            { id: "reliability-compliance", label: "Compliance Control", path: `${base}/reliability/compliance` },
            { id: "reliability-program", label: "Programme", path: `${base}/reliability/program` },
            { id: "reliability-changes", label: "Programme Changes", path: `${base}/reliability/changes` },
            { id: "reliability-handoffs", label: "Module Handoffs", path: `${base}/reliability/handoffs` },
            { id: "reliability-meetings", label: "Review Meetings", path: `${base}/reliability/meetings` },
            { id: "reliability-authority", label: "Authority Packages", path: `${base}/reliability/authority` },
            { id: "reliability-ai", label: "AI Reviews", path: `${base}/reliability/ai` },
            { id: "reliability-reports", label: "Controlled Reports", path: `${base}/reliability/reports` },
            { id: "reliability-data-quality", label: "Data Quality", path: `${base}/reliability/data-quality` },
          ],
        },
      ],
    };
  }
'''
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def harden_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = set(text.splitlines())
    required = [
        ".venv/",
        "venv/",
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        "node_modules/",
        "frontend/dist/",
        "*.db",
    ]
    missing = [item for item in required if item not in lines]
    if not missing:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n# Local environments and generated build/runtime files\n"
    text += "\n".join(missing) + "\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    replace_reliability_navigation()
    harden_gitignore()
    print("Prepared conflict-resolved Reliability clean tree.")
