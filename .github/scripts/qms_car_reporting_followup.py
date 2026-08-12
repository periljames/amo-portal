from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {rel}, found {count}: {old[:160]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


replace_once(
    "frontend/tests/e2e/qms-car-control-loop.spec.ts",
    '''  // Intercept only backend/API traffic. Intercepting every request also replaces\n  // the preview server's JS/CSS assets, preventing the React route from loading.\n  await page.route("**/api/**", fulfil);\n  await page.route("**/auth/**", fulfil);\n  await page.route("**/accounts/**", fulfil);\n''',
    '''  // Route data requests by semantic API path while allowing the Vite document,\n  // JS/CSS chunks, fonts and images to load normally. This covers deployments\n  // where canonical QMS APIs are either root-mounted or prefixed by /api.\n  await page.route("**/*", async (route) => {\n    const request = route.request();\n    const url = request.url();\n    const isQmsData = url.includes("/quality/cars/") || url.includes("/quality/notifications");\n    const isPortalData = url.includes("/auth/") || url.includes("/accounts/") || url.includes("/api/maintenance/");\n    if (isQmsData || isPortalData) {\n      await fulfil(route);\n      return;\n    }\n    await route.continue();\n  });\n''',
)

replace_once(
    "frontend/src/pages/qms/QmsCarPerformanceReportPage.tsx",
    '  const allCars = reportQuery.data?.items ?? [];\n',
    '  const allCars = useMemo(() => reportQuery.data?.items ?? [], [reportQuery.data?.items]);\n',
)

replace_once(
    "frontend/src/pages/qms/QmsCarPerformanceReportPage.tsx",
    '''  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);\n  const generatedAt = useMemo(\n    () => new Date(reportQuery.dataUpdatedAt || Date.now()),\n    [reportQuery.dataUpdatedAt],\n  );\n''',
    '''  const generatedAt = useMemo(\n    () => new Date(reportQuery.dataUpdatedAt || 0),\n    [reportQuery.dataUpdatedAt],\n  );\n  const today = generatedAt.toISOString().slice(0, 10);\n''',
)

replace_once(
    "frontend/tests/e2e/qms-car-performance-report.spec.ts",
    '''  await page.route("**/api/**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });\n  });\n''',
    '''  await page.route("**/api/**", async (route) => {\n    if (route.request().url().includes("/quality/cars/register/paged")) {\n      await route.fallback();\n      return;\n    }\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });\n  });\n''',
)

print("QMS CAR reporting browser follow-up applied")
