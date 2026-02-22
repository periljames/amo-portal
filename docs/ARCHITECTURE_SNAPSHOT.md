# AMO Portal – Architecture Snapshot

## Stack overview
- **Backend:** FastAPI with SQLAlchemy ORM, Alembic migrations, Argon2 password hashing, JWT auth (jose), Postgres-targeted models (naming conventions for migrations). Entrypoint: `amodb.main`.
- **Frontend:** React + TypeScript + Vite. Router-driven single page app with protected routes via localStorage JWT (`services/auth`). Styling via global CSS and modular components.
- **Build/Tooling:** Backend uses `requirements.txt` (Uvicorn, FastAPI, SQLAlchemy, argon2-cffi, jose). Frontend uses Vite toolchain with eslint config and TS configs.

## Key backend modules
- `amodb.database`: configures separate read/write SQLAlchemy engines from `DATABASE_WRITE_URL`/`DATABASE_URL` envs, with pool tuning and dependency helpers.
- `amodb.security`: password hashing (Argon2id + bcrypt compatibility), JWT creation/validation, FastAPI dependencies for current user and role enforcement (`require_roles`, `require_admin`).
- `amodb.apps.accounts`: AMO/department/user models, roles (`AccountRole`), login/password reset routers, admin/user services, AMO asset management (file metadata).
- `amodb.apps.fleet`, `work`, `crs`, `training`, `quality`, `maintenance_program`: domain models/routers for aircraft, work orders/tasking, CRS PDF generation/validation, training records, QMS items, maintenance programme, etc.
- `alembic`: migration scaffolding with an initial migration present.

## Data flow (backend)
1. **Request ingress:** FastAPI app in `amodb.main` attaches CORS middleware and registers routers per domain.
2. **Authentication:** Public `/auth/login` issues JWT via `accounts.services.issue_access_token_for_user`; subsequent calls use `Authorization: Bearer` and `security.get_current_user` dependency.
3. **Routing → Services:** Routers validate payloads with Pydantic schemas (`apps/*/schemas.py`), dispatch to service functions (e.g., `accounts.services`, `fleet.services`), and leverage role dependencies for RBAC.
4. **DB access:** Services use SQLAlchemy sessions from `get_db`/`get_write_db`/`get_read_db`. Models define indices for tenant + role filters.
5. **Response:** Pydantic response models are returned to the frontend; some modules (CRS) can render PDFs via utility helpers.

## Frontend data & state
- **Routing:** `src/router.tsx` defines public login/reset flows and protected maintenance/admin routes guarded by `RequireAuth` (checks `services/auth.isAuthenticated`).
- **Auth state:** `services/auth.ts` manages JWT, AMO/department context, cached user in `localStorage`, and provides `authHeaders` for API calls.
- **Pages/components:** Auth pages (`LoginPage`, `PasswordResetPage`), dashboards (department/admin), CRS creation, aircraft import, QMS, training. Styling via `styles/global.css` and page-specific CSS. Hooks (`useTimeOfDayTheme`, `useColorScheme`) drive theming.

## Current risks / gaps
- **CORS defaults:** Previously allowed `*` with credentials enabled (fixed in this commit to env-driven origins).
- **Secrets:** Default `SECRET_KEY` fallback in `security.py`; needs env override enforcement.
- **Rate limiting / brute-force protection:** None on auth endpoints.
- **File uploads:** AMO assets and CRS templates rely on metadata; need content-type/size checks and storage hardening.
- **RBAC coverage:** Core helpers exist but not uniformly applied across all routers; audit needed.
- **Dependency audits:** No recent npm/pip audit results checked into repo.

## Cron runners
- **QMS task runner:** `python -m amodb.jobs.qms_task_runner` (safe to run via cron for reminders/escalations).

This snapshot should be refreshed after major structural, security, or data-model changes.

## Realtime split architecture update (2026-02-16)
- **SSE (`/api/events` + `/api/events/history`) stays unchanged** and remains the default stream for cockpit/global invalidation.
- **MQTT/WSS is added for user-interactive realtime paths only**:
  - bidirectional chat,
  - user presence,
  - ack workflows (`delivered/read/actioned`) for chat + prompts/tasks.
- Backend now includes a `realtime` module with:
  - strict MessagePack envelope validation (`v=1`),
  - short-lived realtime connect token issuance,
  - tenant/topic guard rails,
  - durable outbox table for broker publish retries.

## Superuser "god mode" and platform AMOs (clarification)
- `system`/`root` platform AMO records are bootstrap control tenants used to anchor platform-level users (including superuser) and system configuration.
- They are expected seed/control-plane tenants; they do not replace customer AMOs.
- Superuser can now authenticate against any AMO slug path (e.g. `/maintenance/<amoSlug>/login`) using the same superuser email/password.
- During superuser login with a target AMO slug, backend now aligns active admin context to that AMO automatically, so API scope follows the selected tenant immediately.
- `/login` now includes **Use Demo Access** quick action to auto-fill demo credentials/slug via environment defaults.
