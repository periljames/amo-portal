# Reliability V5 Staging Diagnostic

- Run: `30844326988`

| Stage | Exit |
|---|---:|
| reconstruct | 128 |
| stage | 0 |
| paths | 1 |
| diffcheck | 0 |
| status | 0 |

## reconstruct
```text
From https://github.com/periljames/amo-portal
 * branch              agent/reliability-v2-foundation -> FETCH_HEAD
 * branch              feat/global-tenant-navigation-quality-home -> FETCH_HEAD
 * branch              agent/reliability-v2-collectors-prep -> FETCH_HEAD
rm 'frontend/src/pages/ReliabilityReportsPage.tsx'
Applied patch to 'backend/amodb/alembic/env.py' cleanly.
Applied patch to 'backend/amodb/main.py' cleanly.
Applied patch to 'frontend/src/app/PortalRouteSurface.tsx' cleanly.
Applied patch to 'frontend/src/app/portalRouteManifest.test.ts' cleanly.
Applied patch to 'frontend/src/app/routePreload.ts' cleanly.
Applied patch to 'frontend/src/portalRoutes.tsx' cleanly.
Prepared conflict-resolved Reliability clean tree.
fatal: invalid reference: agent/reliability-v2-collectors-prep
```

## stage
```text
fatal: pathspec 'frontend/src/pages/ReliabilityReportsPage.tsx' did not match any files
```

## paths
```text
Traceback (most recent call last):
  File "/tmp/rel-stage/validate.py", line 13, in <module>
    import psycopg2
ModuleNotFoundError: No module named 'psycopg2'
```

## diffcheck
```text
```

## status
```text
M	.gitignore
M	backend/amodb/alembic/env.py
M	backend/amodb/apps/reliability/__init__.py
A	backend/amodb/apps/reliability/advanced_models.py
A	backend/amodb/apps/reliability/advanced_router.py
A	backend/amodb/apps/reliability/advanced_scheduler.py
A	backend/amodb/apps/reliability/advanced_schemas.py
A	backend/amodb/apps/reliability/advanced_services.py
M	backend/amodb/apps/reliability/models.py
M	backend/amodb/apps/reliability/router.py
M	backend/amodb/apps/reliability/schemas.py
M	backend/amodb/apps/reliability/services.py
M	backend/amodb/apps/reliability/tests/__init__.py
A	backend/amodb/apps/reliability/tests/test_canonical_foundation.py
A	backend/amodb/apps/reliability/tests/test_complete_scope.py
M	backend/amodb/apps/reliability/tests/test_router.py
M	backend/amodb/main.py
A	docs/reliability/RELIABILITY_CLEAN_REBUILD_VALIDATION.md
A	docs/reliability/RELIABILITY_COMPLETE_SCOPE_VALIDATION.md
A	docs/reliability/RELIABILITY_MODULE_V2_TARGET_DESIGN.md
A	docs/reliability/RELIABILITY_V2_IMPLEMENTATION_TRACKER.md
A	docs/reliability/RELIABILITY_V2_VALIDATION.md
M	frontend/src/app/PortalRouteSurface.tsx
M	frontend/src/app/portalRouteManifest.test.ts
M	frontend/src/app/portalRouteManifest.ts
M	frontend/src/app/routePreload.ts
D	frontend/src/pages/ReliabilityReportsPage.tsx
A	frontend/src/pages/reliability/ReliabilityAdvancedViews.tsx
A	frontend/src/pages/reliability/ReliabilityReportsView.tsx
A	frontend/src/pages/reliability/ReliabilityWorkspacePage.tsx
M	frontend/src/portalRoutes.tsx
M	frontend/src/services/reliability.ts
A	frontend/src/styles/reliability-v2.css
```
