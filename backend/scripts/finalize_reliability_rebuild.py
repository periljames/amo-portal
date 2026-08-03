from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend/src"
BACKEND = ROOT / "backend/amodb/apps/reliability"


def patch_manifest() -> None:
    path = FRONTEND / "app/portalRouteManifest.ts"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'  if \(department === "reliability"\) return \{.*?\n  \};\n'
        r'(?=  if \(department === "safety"\))',
        re.DOTALL,
    )
    replacement = '''  if (department === "reliability") return {
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
          { id: "reliability-program", label: "Programme", path: `${base}/reliability/program` },
          { id: "reliability-changes", label: "Programme Changes", path: `${base}/reliability/changes` },
          { id: "reliability-meetings", label: "Review Meetings", path: `${base}/reliability/meetings` },
          { id: "reliability-reports", label: "Controlled Reports", path: `${base}/reliability/reports` },
          { id: "reliability-data-quality", label: "Data Quality", path: `${base}/reliability/data-quality` },
        ],
      },
    ],
  };
'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected one Reliability navigation branch, found {count}.")
    path.write_text(text, encoding="utf-8")


def patch_navigation_tests() -> None:
    path = FRONTEND / "app/portalRouteManifest.test.ts"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'import { describe, expect, it } from "vitest";',
        'import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";',
        1,
    )
    anchor = '''import {
  buildPortalNavigation,
  flattenPortalNavigation,
  type PortalNavItem,
} from "./portalRouteManifest";
'''
    setup = anchor + '''
const storage = new Map<string, string>();
const localStorageMock: Storage = {
  get length() { return storage.size; },
  clear() { storage.clear(); },
  getItem(key: string) { return storage.get(key) ?? null; },
  key(index: number) { return Array.from(storage.keys())[index] ?? null; },
  removeItem(key: string) { storage.delete(key); },
  setItem(key: string, value: string) { storage.set(key, String(value)); },
};

beforeEach(() => {
  storage.clear();
  vi.stubGlobal("localStorage", localStorageMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});
'''
    if "const localStorageMock" not in text:
        if text.count(anchor) != 1:
            raise RuntimeError("Navigation test import anchor not found.")
        text = text.replace(anchor, setup, 1)

    old = '''    expect(paths.get("reliability-reports")).toBe("/maintenance/tenant-a/reliability/reports");
    expect(paths.get("ehm-dashboard")).toBe("/maintenance/tenant-a/ehm/dashboard");
    expect(paths.get("ehm-trends")).toBe("/maintenance/tenant-a/ehm/trends");
    expect(paths.get("ehm-uploads")).toBe("/maintenance/tenant-a/ehm/uploads");
'''
    new = '''    expect(paths.get("reliability-workbench")).toBe("/maintenance/tenant-a/reliability");
    expect(paths.get("reliability-events")).toBe("/maintenance/tenant-a/reliability/events");
    expect(paths.get("reliability-alerts")).toBe("/maintenance/tenant-a/reliability/alerts");
    expect(paths.get("reliability-fracas")).toBe("/maintenance/tenant-a/reliability/cases");
    expect(paths.get("reliability-fleet")).toBe("/maintenance/tenant-a/reliability/fleet");
    expect(paths.get("reliability-systems")).toBe("/maintenance/tenant-a/reliability/systems");
    expect(paths.get("reliability-components")).toBe("/maintenance/tenant-a/reliability/components");
    expect(paths.get("reliability-engines")).toBe("/maintenance/tenant-a/reliability/engines");
    expect(paths.get("reliability-program")).toBe("/maintenance/tenant-a/reliability/program");
    expect(paths.get("reliability-changes")).toBe("/maintenance/tenant-a/reliability/changes");
    expect(paths.get("reliability-meetings")).toBe("/maintenance/tenant-a/reliability/meetings");
    expect(paths.get("reliability-reports")).toBe("/maintenance/tenant-a/reliability/reports");
    expect(paths.get("reliability-data-quality")).toBe("/maintenance/tenant-a/reliability/data-quality");
    expect(paths.get("ehm-dashboard")).toBe("/maintenance/tenant-a/ehm/dashboard");
    expect(paths.get("ehm-trends")).toBe("/maintenance/tenant-a/ehm/trends");
    expect(paths.get("ehm-uploads")).toBe("/maintenance/tenant-a/ehm/uploads");
'''
    if text.count(old) != 1:
        raise RuntimeError("Reliability route assertions not found.")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_preload() -> None:
    path = FRONTEND / "app/routePreload.ts"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'const loadReliabilityReportsPage: RouteLoader = () => import("../pages/ReliabilityReportsPage");',
        'const loadReliabilityWorkspacePage: RouteLoader = () => import("../pages/reliability/ReliabilityWorkspacePage");',
    )
    text = text.replace(
        '{ test: /\\/reliability(?:\\/|$)/, loaders: [loadReliabilityReportsPage] },',
        '{ test: /\\/reliability(?:\\/|$)/, loaders: [loadReliabilityWorkspacePage] },',
    )
    if "ReliabilityReportsPage" in text or "loadReliabilityReportsPage" in text:
        raise RuntimeError("Legacy Reliability report preload remains.")
    path.write_text(text, encoding="utf-8")


def write_backend_test() -> None:
    path = BACKEND / "tests/test_canonical_foundation.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('''from datetime import datetime, timedelta, timezone

from amodb.apps.reliability.router import router
from amodb.apps.reliability.services import _reliability_freshness


def test_router_exposes_one_canonical_reliability_surface():
    paths = {route.path for route in router.routes}
    assert "/reliability/workbench" in paths
    assert "/reliability/events" in paths
    assert "/reliability/events/{event_id:int}" in paths
    assert "/reliability/alerts" in paths
    assert "/reliability/alerts/{alert_id:int}" in paths
    assert "/reliability/fracas/cases" in paths
    assert "/reliability/fracas/cases/{case_id:int}" in paths
    assert "/reliability/fracas/cases/{case_id:int}/actions" in paths
    assert "/reliability/engine-trends/fleet-status" in paths
    assert all("/v2" not in route_path for route_path in paths)
    assert "/reliability/fracas/{fracas_case_id}/actions" not in paths


def test_freshness_never_marks_missing_data_current():
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    missing = _reliability_freshness(source="Missing", latest=None, now=now)
    stale = _reliability_freshness(source="Stale", latest=now - timedelta(days=8), now=now)
    current = _reliability_freshness(source="Current", latest=now - timedelta(days=1), now=now)
    assert missing.status == "MISSING"
    assert stale.status == "STALE"
    assert current.status == "CURRENT"
''', encoding="utf-8")


def main() -> None:
    patch_manifest()
    patch_navigation_tests()
    patch_preload()
    write_backend_test()
    print("Canonical Reliability navigation, preload and contract tests finalized.")


if __name__ == "__main__":
    main()
