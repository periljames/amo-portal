# Portal Go Live Master Switch

## What it does
- Adds a **Go Live (Master)** button on the Superuser **Admin Dashboard → AMO Context** panel.
- Forces admin context to `REAL` mode on a non-demo AMO.
- Writes a global runtime flag (`amodb_portal_go_live=1`) in local storage.
- Broadcasts a runtime event (`amodb:runtime-mode`) so pages can react immediately.

## Runtime behavior after Go Live
- Demo mode toggle is locked on Superuser pages.
- EHM demo-mode hook (`useEhmDemoMode`) is forced off and cannot be re-enabled while Go Live is active.
- QMS cockpit services stop returning mock fallback payloads on API failure and instead raise live-mode errors.

## Primary files
- `frontend/src/pages/AdminDashboardPage.tsx`
- `frontend/src/services/runtimeMode.ts`
- `frontend/src/hooks/useEhmDemoMode.ts`
- `frontend/src/services/qmsCockpit.ts`

## Notes for production
- This switch is **frontend global** for the active browser session/profile.
- To revert locally (for non-production testing), clear `amodb_portal_go_live` in browser storage or set it to `0`.


## Portal-wide confirmation surfaces
- Top bar now shows runtime chip on all pages:
  - `LIVE · GARMIN LINK` when Go Live is active.
  - `DEMO · SIM MODE` when demo runtime is active.
- Superuser Overview includes a Garmin-style flight deck panel with runtime mode, pipeline state, last backend check, and a direct link to the Go Live master control.

## Engineering rule for future changes
- Any new frontend service that currently returns mock/demo fallback **must** gate that fallback behind `shouldUseMockData()`.
- Any new superuser operational dashboard should expose the current runtime mode from `runtimeMode` (or `usePortalRuntimeMode`) to avoid ambiguous environments.

## Maintenance module runtime-mode alignment (this run)
- `/maintenance/*` pages now honor the existing portal runtime switch:
  - `DEMO` mode (`amodb_portal_go_live=0`): maintenance demo/local datasets are visible for Non-Routines, Inspections/Holds, Parts/Tools and demo defect fallback.
  - `LIVE` mode (`amodb_portal_go_live=1`): demo/local mutation is disabled on maintenance forms so operational users do not mix sandbox values into live workflows.
- Maintenance header now shows explicit runtime pill (`DEMO DATA MODE` / `LIVE DATA MODE`) and a guidance banner in demo mode.
- No new runtime flag was introduced; implementation reuses `shouldUseMockData()` and `usePortalRuntimeMode()`.
