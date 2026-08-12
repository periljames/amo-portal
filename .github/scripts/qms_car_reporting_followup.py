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
    '''  // The staged control-loop service uses tenant-scoped /api paths, while the\n  // established CAR response/evidence services use canonical root /quality paths.\n  // Intercept the exact root CAR API shapes without catching the React page route.\n  await page.route(`**/quality/cars/${CAR_ID}/responses**`, fulfil);\n  await page.route(`**/quality/cars/${CAR_ID}/attachments**`, fulfil);\n  await page.route(`**/quality/cars/${CAR_ID}/invite**`, fulfil);\n  await page.route("**/quality/cars/assignees**", fulfil);\n  await page.route("**/quality/notifications**", fulfil);\n  await page.route("**/api/**", fulfil);\n  await page.route("**/auth/**", fulfil);\n  await page.route("**/accounts/**", fulfil);\n''',
)

replace_once(
    "frontend/src/pages/qms/QmsCarPerformanceReportPage.tsx",
    '  const allCars = reportQuery.data?.items ?? [];\n',
    '  const allCars = useMemo(() => reportQuery.data?.items ?? [], [reportQuery.data?.items]);\n',
)

print("QMS CAR reporting browser follow-up applied")
