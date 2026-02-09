# AMO Portal Phase 0 Audit Summary

## A) Repo structure audit

### App shell / layout / scroll containers
- **Primary layout:** `DepartmentLayout` wraps nearly all authenticated pages and renders the shared shell using `AppShell` (sidebar + header + main). The layout currently relies on the `<body>` scroll rather than a single dedicated content scroll container. The sidebar is part of the same grid layout, so the sidebar scrolls with the page when content grows beyond the viewport. (`frontend/src/components/Layout/DepartmentLayout.tsx`, `frontend/src/components/AppShell/AppShell.tsx`, `frontend/src/styles/global.css`)
- **Auth layout:** `AuthLayout` handles login/onboarding experiences. (`frontend/src/components/Layout/AuthLayout.tsx`)
- **Sidebar + header ownership:** The sidebar and header are built in `DepartmentLayout` and styled in `global.css` (`.app-shell`, `.app-shell__sidebar`, `.app-shell__main`).

### Routing architecture
- Routes are centrally defined in `frontend/src/router.tsx` with protected routing (`RequireAuth`) and optional tenant admin gating (`RequireTenantAdmin`).
- Department landing pages use the dynamic segment `:department` and map into multiple module pages (work orders, training, QMS, reliability, etc.).
- The comprehensive route list is documented in `ROUTE_MAP.md`.

### UI primitives / token system
- Global tokens are defined in `frontend/src/styles/global.css` (`:root` + `body[data-color-scheme="light"]`), providing base surfaces, borders, text, and accent colors.
- There is **partial** semantic token coverage, but reuse is inconsistent across cards/tiles with some hardcoded colors in components. This drives readability issues in light mode and inconsistent contrast across cards.

## B) Data/API audit

### QMS and related backend endpoints (Quality, Training, Documents, CAR/CAPA, Audits)
- **Quality QMS core (prefix `/quality`)** — see `backend/amodb/apps/quality/router.py`:
  - `/quality/qms/dashboard` (dashboard summary)
  - `/quality/qms/documents` (GET/POST/PATCH, revisions, publish, distribute, acknowledge)
  - `/quality/qms/distributions` (GET/POST/ack)
  - `/quality/qms/change-requests` (GET/POST/PATCH)
  - `/quality/audits` + `/quality/audits/schedules` (GET/POST/PATCH)
  - `/quality/audits/:id/checklist` and `/quality/audits/:id/report` (generate/download)
  - `/quality/audits/:id/findings` + `/quality/findings/:id/close|verify|ack`
  - `/quality/cars` + `/quality/cars/:id` (CAR/CAPA create/update)
  - `/quality/cars/:id/attachments|invite|review|actions|reminders|escalate`
  - `/quality/notifications/me` (QMS notification list) and `/quality/notifications/:id/read`
- **Training (prefix `/training`)** — see `backend/amodb/apps/training/router.py` for the full list of training, deferrals, training events, and evidence packs.
- **Tasks (prefix `/tasks`)** — see `backend/amodb/apps/tasks/router.py` for `/tasks/my`, `/tasks`, and task update endpoints.

### User profiles / roles / authorization
- **Auth:** `/auth/login`, `/auth/me`, `/auth/password-reset/*` (see `backend/amodb/apps/accounts/router_public.py`).
- **Admin users & roles:** `/accounts/admin/users`, `/accounts/admin/users/:id`, role/department updates, password resets, user deletion (see `backend/amodb/apps/accounts/router_admin.py`).
- **Tenant admin / AMO settings:** `/accounts/admin/*` + `/admin/tenants/*` (see `backend/amodb/apps/accounts/router_admin.py`, `router_modules_admin.py`).

### Fetch layer / auth injection
- Frontend uses `fetch` directly across services with a shared `getApiBaseUrl()` and `getToken()` from `services/auth.ts`. (`frontend/src/services/*.ts`)
- There is a small shared request wrapper in `services/crs.ts` and some inline `fetch` calls in other services.
- Auth handling is implemented in `services/auth.ts` with `handleAuthFailure` on 401 responses.

### Realtime support
- No SSE or WebSocket endpoints were found in the backend.
- No `EventSource` or WebSocket usage exists in the frontend.
- `websockets` is present in backend requirements but not wired into any module.

## C) UX bug audit (fix list)

1) **Sidebar scroll coupling:** The sidebar and header are part of the same document scroll, causing the sidebar to move with content instead of remaining fixed. This violates the cockpit requirement. (`frontend/src/styles/global.css`)
2) **Token mismatch / contrast issues:** Some cards and components use hard-coded colors or partial token coverage, which can cause low contrast in light mode and inconsistent readability. (`frontend/src/styles/global.css`, usage throughout `frontend/src/components` and `frontend/src/pages`)
3) **Dead space / low information density:** Dashboard pages (e.g., `DashboardPage`, `QMSHomePage`, `QMSKpisPage`) use wide margins and stacked card layouts with limited density. (`frontend/src/pages`)
4) **Redundant headers / controls:** Multiple pages repeat banners/headers inside `DepartmentLayout` without cohesive hierarchy, contributing to wasted space.
5) **No realtime indicator:** The UI relies on manual refresh/implicit fetches; there is no live state indicator or automatic invalidation strategy.

## D) Upgrade plan + risk mitigation (high-level)

1) **AppShellV2 (feature-flagged):**
   - Introduce a fixed sidebar and a single scrollable content container within the shell.
   - Add focus mode for cockpit routes, replacing the sidebar with a compact launcher.
   - Keep AppShellV1 intact and behind a feature flag for safe rollback.

2) **Token system and contrast guardrails:**
   - Add semantic tokens for text/surface/border and enforce them at card/KPI primitives.
   - Remove hardcoded white text or mismatched surface colors in shared components.

3) **Realtime pipeline:**
   - Add minimal SSE endpoint (`/api/events` or `/qms/events`) and broadcast domain-aware events.
   - Integrate React Query for caching/invalidation with a debounced SSE event handler.
   - Provide fallback periodic revalidation when SSE is unavailable.

4) **Dashboard scaffold + per-department configs:**
   - Implement config-driven cockpit layers with specific drilldowns and right-rail activity feed.
   - All drilldowns must route to filtered list pages or specific entity views.

5) **Performance and motion:**
   - Centralized motion primitives and reduced-motion handling.
   - Virtualized action queues, code-split charts, and memoized widgets.

Risk mitigation:
- Ship new shell and cockpit behind a feature flag.
- Preserve existing routes and add additive routes for new drilldown filters.
- No API contract changes; add endpoints only where required for SSE or new actions.
- Add monitoring / logging around SSE consumption to detect event storms.
