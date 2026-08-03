# Reliability Tenant-Shell Merge Diagnostic

- Run: `30808533950`
- Reliability source SHA: `f3696572c8d6ae78085688093f90017b69a07bc2`
- Fetched shell SHA: `309a8eac0aecfdbb19a1ecd71c83cdbaababb074`
- Merge exit code: `0`

## Conflicted files

```text

```

## Merge log

```text
Merge made by the 'ort' strategy.
 .github/workflows/main-merge-readiness.yml         | 124 ++-
 .github/workflows/publications-reader-ci.yml       |  96 +++
 .../workflows/tenant-navigation-quality-home.yml   |  10 +-
 .../amodb/apps/accounts/department_home_router.py  |  28 +-
 .../tests/test_department_home_security.py         |  17 +
 frontend/package.json                              |   1 +
 frontend/playwright.tenant.config.ts               |  23 +
 frontend/src/hooks/usePortalAppearance.ts          |   5 +
 frontend/src/pages/DepartmentHomePage.tsx          |  20 +-
 .../src/pages/procurement/ProcurementModule.tsx    | 906 +++++++++++++++++++++
 frontend/src/styles/department-home.css            |  41 +-
 frontend/src/styles/foundations/layout-safety.css  |  30 +-
 frontend/src/styles/index.css                      |   5 +-
 frontend/src/styles/theme-contract.css             | 162 +---
 frontend/tests/e2e/tenant-shell-theme.spec.ts      | 191 +++++
 frontend/tsconfig.app.json                         |   2 +-
 16 files changed, 1389 insertions(+), 272 deletions(-)
 create mode 100644 frontend/playwright.tenant.config.ts
 create mode 100644 frontend/src/pages/procurement/ProcurementModule.tsx
 create mode 100644 frontend/tests/e2e/tenant-shell-theme.spec.ts
```

## Status

```text

```
