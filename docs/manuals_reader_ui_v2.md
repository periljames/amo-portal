# Manuals Reader UI V2 (Branding + Exit + Standalone Plugin)

## What was implemented

### 1) Tenant branding contract
- Backend endpoint: `GET /api/tenants/:tenantSlug/branding`.
- Response includes tenant display/logo, accent colors, default theme, and reader-specific visual preferences.
- Frontend `TenantBrandingProvider` fetches branding and applies CSS vars:
  - `--tenant-accent`
  - `--tenant-bg`
  - `--paper`
  - `--ink`

### 2) Professional reader shell
- Added `ManualsReaderShell` with three-zone header:
  - Left: Exit button, tenant identity, manual chip.
  - Center: location label.
  - Right: status badge, rev meta, layout selector, zoom controls, focus, fullscreen, TOC/Inspector toggles.
- Exit behavior:
  - Embedded mode: back to `/t/:tenantSlug/manuals`.
  - Standalone mode: uses `VITE_PORTAL_URL` fallback to `/`.
  - Optional close action when opened by another window.

### 3) Focus + Fullscreen
- Focus state persisted per user in local storage.
- Fullscreen uses Fullscreen API and shows 3-second “Esc to exit fullscreen” hint.

### 4) Viewer modes
- **Continuous mode**: structured HTML blocks, active hyperlinks, table/image styling, change bars.
- **Paged mode**: 1-up/2-up/3-up page grids with row virtualization (`@tanstack/react-virtual`) for smoother scrolling.

### 5) Standalone-capable packaging
- Added a plugin package at `frontend/src/packages/manuals-reader/` exporting:
  - `ManualsReaderApp`
  - `ManualsReaderRoutes`
  - `ManualsReaderShell`
- Added standalone entrypoint scaffold:
  - `frontend/src/standalone/manuals-main.tsx`

## Notes
- Pagination currently uses reader-side chunked page cards with virtualization. This sets the foundation for future Paged.js-driven page-fragment rendering.
- Reader stores last position (`manuals.position.<revId>`), layout, zoom, and focus mode.

## API surface used by Reader V2
- `GET /api/tenants/:tenantSlug/branding`
- `GET /manuals/t/:tenantSlug/:manualId/revisions`
- `GET /manuals/t/:tenantSlug/:manualId/rev/:revId/read`
- `GET /manuals/t/:tenantSlug/:manualId/rev/:revId/diff`
- `GET /manuals/t/:tenantSlug/:manualId/rev/:revId/workflow`
- `POST /manuals/t/:tenantSlug/:manualId/rev/:revId/acknowledge`
- `POST /manuals/t/:tenantSlug/:manualId/rev/:revId/exports`


## UI V2.1 adjustments
- Topbar now uses token-driven background/ink and remains a single sticky row.
- Added deterministic QMS document viewer route compatibility.
- Added SSE refresh hooks with `lastEventId` query replay and `reset` event handling.
- Added role-based gate for disabling uncontrolled watermark / enabling controlled hard copy.
