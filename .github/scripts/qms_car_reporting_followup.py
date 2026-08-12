from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {rel}, found {count}: {old[:180]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


replace_once(
    "frontend/tests/e2e/qms-car-control-loop.spec.ts",
    '''  // Intercept only backend/API traffic. Intercepting every request also replaces\n  // the preview server's JS/CSS assets, preventing the React route from loading.\n  await page.route("**/api/**", fulfil);\n  await page.route("**/auth/**", fulfil);\n  await page.route("**/accounts/**", fulfil);\n''',
    '''  await page.route("**/*", async (route) => {\n    const url = route.request().url();\n    const isQmsData = url.includes("/quality/cars/") || url.includes("/quality/notifications");\n    const isPortalData = url.includes("/auth/") || url.includes("/accounts/") || url.includes("/api/maintenance/");\n    if (isQmsData || isPortalData) { await fulfil(route); return; }\n    await route.continue();\n  });\n''',
)
replace_once(
    "frontend/tests/e2e/qms-car-control-loop.spec.ts",
    '  await expect(page.getByDisplayValue("Engineering approval required before implementation evidence can be accepted.")).toBeVisible();\n',
    '  await expect(page.getByRole("heading", { name: "Dependency detail editor" }).locator("xpath=ancestor::section[1]").locator("textarea").first()).toHaveValue("Engineering approval required before implementation evidence can be accepted.");\n',
)
replace_once(
    "frontend/src/pages/qms/QmsCarPerformanceReportPage.tsx",
    '  const allCars = reportQuery.data?.items ?? [];\n',
    '  const allCars = useMemo(() => reportQuery.data?.items ?? [], [reportQuery.data?.items]);\n',
)
replace_once(
    "frontend/src/pages/qms/QmsCarPerformanceReportPage.tsx",
    '''  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);\n  const generatedAt = useMemo(\n    () => new Date(reportQuery.dataUpdatedAt || Date.now()),\n    [reportQuery.dataUpdatedAt],\n  );\n''',
    '''  const generatedAt = useMemo(() => new Date(reportQuery.dataUpdatedAt || 0), [reportQuery.dataUpdatedAt]);\n  const today = generatedAt.toISOString().slice(0, 10);\n''',
)
replace_once(
    "frontend/tests/e2e/qms-car-performance-report.spec.ts",
    '''  await page.route("**/auth/**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });\n  });\n  await page.route("**/accounts/**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });\n  });\n  await page.route("**/api/**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });\n  });\n''',
    '''  await page.route("**/auth/portal-preferences/**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-12T08:00:00Z" }) });\n  });\n  await page.route("**/accounts/admin/admin-profile/**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });\n  });\n  await page.route("**/quality/notifications**", async (route) => {\n    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });\n  });\n''',
)
replace_once(
    "frontend/tests/e2e/qms-car-performance-report.spec.ts",
    '''  await expect(page.getByText("Engineering", { exact: true }).first()).toBeVisible();\n  await expect(page.getByText("Quality", { exact: true }).first()).toBeVisible();\n''',
    '''  const departmentSection = page.getByRole("heading", { name: "Department performance" }).locator("xpath=ancestor::section[1]");\n  await expect(departmentSection.getByText("Engineering", { exact: true })).toBeVisible();\n  await expect(departmentSection.getByText("Quality", { exact: true })).toBeVisible();\n''',
)
replace_once(
    "frontend/src/router.tsx",
    'const QmsAuditProgrammeSchedulePage = lazy(() => import("./pages/qms/QmsAuditProgrammeSchedulePage"));\n',
    'const QmsAuditProgrammeSchedulePage = lazy(() => import("./pages/qms/QmsAuditProgrammeSchedulePage"));\nconst QmsCarPerformanceReportPage = lazy(() => import("./pages/qms/QmsCarPerformanceReportPage"));\n',
)
replace_once(
    "frontend/src/router.tsx",
    '''function QmsAuditProgrammeScheduleRouteSurface() {\n  return (\n    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading audit programme scheduler…</div></div>}>\n      <WorkspaceRequireAuth><QmsAuditProgrammeSchedulePage /></WorkspaceRequireAuth>\n    </Suspense>\n  );\n}\n''',
    '''function QmsAuditProgrammeScheduleRouteSurface() {\n  return (\n    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading audit programme scheduler…</div></div>}>\n      <WorkspaceRequireAuth><QmsAuditProgrammeSchedulePage /></WorkspaceRequireAuth>\n    </Suspense>\n  );\n}\n\nfunction QmsCarPerformanceReportRouteSurface() {\n  return (\n    <Suspense fallback={<div className="page-loading" role="status"><div className="page-loading__card">Loading CAR performance…</div></div>}>\n      <WorkspaceRequireAuth><QmsCarPerformanceReportPage /></WorkspaceRequireAuth>\n    </Suspense>\n  );\n}\n''',
)
replace_once(
    "frontend/src/router.tsx",
    '''function isSupportedAuditProgrammeSchedulePath(pathname: string): boolean {\n''',
    '''function isSupportedCarPerformanceReportPath(pathname: string): boolean {\n  const parts = pathSegments(pathname);\n  const qualityIndex = parts.indexOf("quality");\n  if (qualityIndex < 0) return false;\n  const relative = parts.slice(qualityIndex + 1);\n  return relative.length === 2 && relative[0] === "reports" && relative[1] === "car-performance";\n}\n\nfunction isSupportedAuditProgrammeSchedulePath(pathname: string): boolean {\n''',
)
replace_once(
    "frontend/src/router.tsx",
    '''  if (isSupportedAuditProgrammeSchedulePath(location.pathname)) return <QmsAuditProgrammeScheduleRouteSurface />;\n  if (qmsRoute.kind === "overview") return <QmsOverviewRouteSurface />;\n  if (isQmsRegisterWorkspace(qmsRoute)) return <QmsRegisterRouteSurface />;\n''',
    '''  if (isSupportedAuditProgrammeSchedulePath(location.pathname)) return <QmsAuditProgrammeScheduleRouteSurface />;\n  if (isSupportedCarPerformanceReportPath(location.pathname)) return <QmsCarPerformanceReportRouteSurface />;\n  if (qmsRoute.kind === "overview") return <QmsOverviewRouteSurface />;\n  if (isQmsRegisterWorkspace(qmsRoute)) return <QmsRegisterRouteSurface />;\n''',
)

print("QMS CAR reporting browser follow-up applied")
