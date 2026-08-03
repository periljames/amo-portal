# Reliability Publication Diagnostic

- Run: `30807925071`
- Source SHA: `b6729c76d87e327e9541ac5dffbb35279f6d0e19`
- Test commit: `3fab359a608d43883759b1ed41f7a68d46ae0a6c`

| Stage | Exit code |
|---|---:|
| Canonical replacement | 0 |
| Finalizer | 0 |
| Route surface patch | 0 |
| Sanitization | 0 |
| Git add | 0 |
| Git diff check | 2 |
| Local commit | 0 |

### status

```text
 D .github/workflows/reliability-git-diagnostic.yml
 D backend/__pycache__/sitecustomize.cpython-312.pyc
 M backend/amodb/apps/reliability/__init__.py
 M backend/amodb/apps/reliability/router.py
 M backend/amodb/apps/reliability/schemas.py
 M backend/amodb/apps/reliability/services.py
 M backend/amodb/apps/reliability/tests/__init__.py
 D backend/scripts/finalize_reliability_rebuild.py
 D backend/scripts/patch_reliability_route_surface.py
 D docs/reliability/.canonical-rebuild-trigger
 D docs/reliability/.push-probe
 D docs/reliability/CANONICAL_REBUILD_DIAGNOSTIC.md
 D docs/reliability/FRONTEND_REBUILD_DIAGNOSTIC.md
 M frontend/src/App.tsx
 M frontend/src/app/PortalRouteSurface.tsx
 M frontend/src/app/portalRouteManifest.test.ts
 M frontend/src/app/portalRouteManifest.ts
 M frontend/src/app/routePreload.ts
 D frontend/src/pages/ReliabilityReportsPage.tsx
 M frontend/src/portalRoutes.tsx
 M frontend/src/services/reliability.ts
?? backend/amodb/apps/reliability/tests/test_canonical_foundation.py
?? docs/reliability/RELIABILITY_MODULE_V2_TARGET_DESIGN.md
?? docs/reliability/RELIABILITY_V2_IMPLEMENTATION_TRACKER.md
?? docs/reliability/RELIABILITY_V2_VALIDATION.md
?? frontend/src/pages/reliability/
?? frontend/src/styles/reliability-v2.css

```

### check

```text
backend/amodb/apps/reliability/schemas.py:962: new blank line at EOF.
docs/reliability/RELIABILITY_V2_IMPLEMENTATION_TRACKER.md:43: new blank line at EOF.

```

### commit

```text
[agent/reliability-v2-foundation 3fab359a] Rebuild Reliability as one canonical module
 28 files changed, 1816 insertions(+), 1198 deletions(-)
 delete mode 100644 .github/workflows/reliability-git-diagnostic.yml
 delete mode 100644 backend/__pycache__/sitecustomize.cpython-312.pyc
 create mode 100644 backend/amodb/apps/reliability/tests/test_canonical_foundation.py
 delete mode 100644 backend/scripts/finalize_reliability_rebuild.py
 delete mode 100644 backend/scripts/patch_reliability_route_surface.py
 delete mode 100644 docs/reliability/.canonical-rebuild-trigger
 delete mode 100644 docs/reliability/.push-probe
 delete mode 100644 docs/reliability/CANONICAL_REBUILD_DIAGNOSTIC.md
 delete mode 100644 docs/reliability/FRONTEND_REBUILD_DIAGNOSTIC.md
 create mode 100644 docs/reliability/RELIABILITY_MODULE_V2_TARGET_DESIGN.md
 create mode 100644 docs/reliability/RELIABILITY_V2_IMPLEMENTATION_TRACKER.md
 create mode 100644 docs/reliability/RELIABILITY_V2_VALIDATION.md
 delete mode 100644 frontend/src/pages/ReliabilityReportsPage.tsx
 create mode 100644 frontend/src/pages/reliability/ReliabilityReportsView.tsx
 create mode 100644 frontend/src/pages/reliability/ReliabilityWorkspacePage.tsx
 create mode 100644 frontend/src/styles/reliability-v2.css

```
