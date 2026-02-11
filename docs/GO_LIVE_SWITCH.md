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
