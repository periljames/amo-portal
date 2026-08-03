# Reliability Clean Overlay Diagnostic

- Run: `30838696775`

| Stage | Exit |
|---|---:|
| fetch | 0 |
| overlay | 0 |
| make patch | 0 |
| apply patch | 1 |
| status | 0 |

## fetch
```text
From https://github.com/periljames/amo-portal
 * branch              agent/reliability-v2-foundation -> FETCH_HEAD
 * branch              feat/global-tenant-navigation-quality-home -> FETCH_HEAD
```

## overlay
```text
```

## make-patch
```text
```

## apply
```text
Applied patch to 'backend/amodb/alembic/env.py' cleanly.
Applied patch to 'backend/amodb/main.py' cleanly.
Applied patch to 'frontend/src/App.tsx' with conflicts.
Applied patch to 'frontend/src/app/PortalRouteSurface.tsx' cleanly.
Applied patch to 'frontend/src/app/portalRouteManifest.test.ts' cleanly.
Applied patch to 'frontend/src/app/portalRouteManifest.ts' with conflicts.
Applied patch to 'frontend/src/app/routePreload.ts' cleanly.
Applied patch to 'frontend/src/portalRoutes.tsx' cleanly.
U frontend/src/App.tsx
U frontend/src/app/portalRouteManifest.ts
```

## status
```text
M  backend/amodb/alembic/env.py
M  backend/amodb/apps/reliability/__init__.py
A  backend/amodb/apps/reliability/advanced_models.py
A  backend/amodb/apps/reliability/advanced_router.py
A  backend/amodb/apps/reliability/advanced_scheduler.py
A  backend/amodb/apps/reliability/advanced_schemas.py
A  backend/amodb/apps/reliability/advanced_services.py
M  backend/amodb/apps/reliability/models.py
M  backend/amodb/apps/reliability/router.py
M  backend/amodb/apps/reliability/schemas.py
M  backend/amodb/apps/reliability/services.py
M  backend/amodb/apps/reliability/tests/__init__.py
A  backend/amodb/apps/reliability/tests/test_canonical_foundation.py
A  backend/amodb/apps/reliability/tests/test_complete_scope.py
M  backend/amodb/apps/reliability/tests/test_router.py
M  backend/amodb/main.py
UU frontend/src/App.tsx
M  frontend/src/app/PortalRouteSurface.tsx
M  frontend/src/app/portalRouteManifest.test.ts
UU frontend/src/app/portalRouteManifest.ts
M  frontend/src/app/routePreload.ts
A  frontend/src/pages/reliability/ReliabilityAdvancedViews.tsx
A  frontend/src/pages/reliability/ReliabilityReportsView.tsx
A  frontend/src/pages/reliability/ReliabilityWorkspacePage.tsx
M  frontend/src/portalRoutes.tsx
M  frontend/src/services/reliability.ts
A  frontend/src/styles/reliability-v2.css
```
