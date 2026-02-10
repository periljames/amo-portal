# AMO Portal – Security Report (Initial Sweep)

| Severity | Area | Issue | Recommendation | Status / Verification |
| --- | --- | --- | --- | --- |
| High | CORS | CORS allowed `*` with credentials enabled in `amodb.main`. | Make origins env-driven and disallow credentials when wildcard is used. | **Addressed** in this commit (`CORS_ALLOWED_ORIGINS` parsing; defaults to localhost) via code review. |
| High | Secrets | `SECRET_KEY` in `security.py` falls back to `CHANGE_ME_IN_PRODUCTION`. | Require `SECRET_KEY` env in production builds; add startup guard or env validation. | Open. Verified by reading `amodb/security.py`. |
| High | Auth endpoints | No rate limiting or brute-force protection on `/auth/login` and password reset routes. | Introduce rate limiting (e.g., slowapi/Redis) and IP/user lockouts; log/alert suspicious attempts. | Open. Observed in `apps/accounts/router_public.py`. |
| Medium | File uploads | AMO asset upload paths/validation not enforced (metadata stored only). Risk of oversized or unsafe uploads. | Add MIME/extension allowlist, size caps, randomised storage paths outside web root, and optional AV scan hook. | Open. Observed in `apps/accounts` asset handling. |
| Medium | RBAC coverage | Role dependencies exist but not uniformly applied across all routers (fleet/work/quality). | Audit routers, wrap sensitive routes with `require_roles`/`require_admin`, and add tests. | Open. Spot-checked routers under `amodb/apps`. |
| Medium | Dependency hygiene | No documented npm/pip audit results; versions may be stale. | Run `pip list --outdated`/`npm audit`, patch criticals, pin versions. | Open. No audit artifacts present. |
| Low | Logging privacy | Authentication services capture IP/User-Agent for audit, but broader request logging settings are unclear. | Ensure sensitive tokens/passwords are not logged and add redaction filters if enabling structured logs. | Open. Requires log config review. |

Next actions should prioritise secrets enforcement, auth rate limiting, and upload hardening. Update this report after mitigations land and include verification steps (tests, configs).


## Changed in this run (2026-02-10)
- **SECRET_KEY enforcement**: **Addressed (production fail-fast)**.
  - Implementation: `backend/amodb/security.py` enforces non-default SECRET_KEY when `APP_ENV/ENV` is `prod/production`.
  - Verification: run API with `APP_ENV=production` and missing/default SECRET_KEY; process exits with RuntimeError.
- **Auth rate limiting**: **Partially addressed** (in-memory implementation for auth-critical endpoints).
  - Implementation: `backend/amodb/apps/accounts/router_public.py` applies `_enforce_auth_rate_limit` on login and password reset endpoints.
  - Verification: burst requests from same IP exceed threshold and return HTTP 429.
- **Upload hardening**: **Partially addressed** for CAR attachments.
  - Implementation: allowlisted MIME/extensions + size caps + sanitized filenames + random storage names + SHA-256 persisted (`quality_car_attachments.sha256`) in `backend/amodb/apps/quality/router.py` and model/migration updates.
  - Verification: upload disallowed type returns 415; >10MB returns 413; accepted file persists with SHA-256 metadata.

## Changed in this run (2026-02-10)
- **Files changed:**
  - `frontend/src/components/realtime/RealtimeProvider.tsx`
  - `frontend/src/components/realtime/LiveStatusIndicator.tsx`
  - `frontend/src/components/Layout/DepartmentLayout.tsx`
- **Security-relevant changes:**
  - No new backend endpoints were introduced in this run.
  - Manual refresh now invalidates an allowlisted set of React Query keys instead of global query invalidation, reducing accidental broad data exposure in mixed-role sessions.
- **RBAC for new endpoints:** none (no endpoint additions).
- **Commands run:** `npx tsc -b`
- **Verification:**
  1. Confirm focus-mode launcher and edge-peek reveal only navigation UI (no direct privileged action changes).
  2. Confirm stale refresh button does not force page reload and only re-fetches existing authorized queries.
- **Known issues:** user action endpoints (disable/revoke/reset password) remain a backend gap for complete cockpit command workflows.
- **Screenshots:** `browser:/tmp/codex_browser_invocations/19aa7325a4460d99/artifacts/artifacts/cockpit-shell-updates.png`

## Changed in this run (2026-02-10)
- **Files changed:**
  - `backend/amodb/apps/accounts/router_admin.py`
  - `backend/amodb/apps/accounts/models.py`
  - `backend/amodb/security.py`
  - `backend/amodb/alembic/versions/z9y8x7w6v5u4_add_user_token_revoked_at.py`
- **Security/RBAC changes:**
  - Added explicit RBAC-protected user command endpoints under `/accounts/admin/users/:id/commands/*` guarded by `require_admin` and AMO scoping.
  - Added token revocation timestamp (`users.token_revoked_at`) and JWT `iat` validation to invalidate sessions after revoke/reset commands.
  - Force-password-reset command now sets `must_change_password=true` and revokes pre-existing tokens.
- **Verification:**
  1. Run command endpoint as AMO admin in-scope user (expect 200).
  2. Run command endpoint against out-of-scope user (expect 404/forbidden behavior).
  3. Confirm revoked token fails `get_current_user` checks after `token_revoked_at` update.
- **New endpoints + RBAC:**
  - `POST /accounts/admin/users/:id/commands/disable` — AMO_ADMIN/SUPERUSER scoped.
  - `POST /accounts/admin/users/:id/commands/enable` — AMO_ADMIN/SUPERUSER scoped.
  - `POST /accounts/admin/users/:id/commands/revoke-access` — AMO_ADMIN/SUPERUSER scoped.
  - `POST /accounts/admin/users/:id/commands/force-password-reset` — AMO_ADMIN/SUPERUSER scoped.
  - `POST /accounts/admin/users/:id/commands/notify` — AMO_ADMIN/SUPERUSER scoped.
  - `POST /accounts/admin/users/:id/commands/schedule-review` — AMO_ADMIN/SUPERUSER scoped.
- **Commands run:**
  - `python -m py_compile ...`
  - `cd backend && pytest amodb/apps/accounts/tests/test_user_commands.py -q`
- **Known issues:**
  - Session revocation is JWT timestamp-based (`iat`) and does not currently maintain per-token server-side blacklist.
- **Screenshots:**
  - `browser:/tmp/codex_browser_invocations/e7a34149932062de/artifacts/artifacts/user-command-center.png`

## Changed in this run (2026-02-10)
- **Files changed:**
  - `frontend/src/components/dashboard/DashboardScaffold.tsx`
  - `frontend/src/utils/featureFlags.ts`
- **Security-relevant notes:**
  - Cursor halo/magnetic layer is explicitly feature-flagged (`VITE_UI_CURSOR_LAYER`) and disabled on touch/reduced-motion contexts to avoid degraded accessibility behavior.
  - No auth/RBAC or endpoint-scope changes in this run.
- **Commands run:**
  - `cd frontend && npm audit --audit-level=high --json`
- **Verification steps:**
  1. Confirm `VITE_UI_CURSOR_LAYER=0` disables pointer layer.
  2. Confirm touch/reduced-motion disables pointer layer even when feature flag is on.
  3. Confirm no new network endpoints are introduced by cockpit interaction changes.
- **Known issues:**
  - Cursor interaction currently cockpit-scoped; no global policy toggle surfaced in user settings yet.
- **Screenshots/artifacts:**
  - `browser:/tmp/codex_browser_invocations/4ded072f3d2512cf/artifacts/artifacts/cockpit-virtual-feed-cursor-layer.png`
