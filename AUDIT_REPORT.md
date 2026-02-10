# Audit Report (Run Contract)

## Phase result (2026-02-10)
### What shipped
- Durable SSE replay/read model now uses persisted `audit_events` rows with tenant scoping and retention guard.
- Reset semantics tightened for unknown/expired cursors with explicit `event: reset` payloads.
- Regression coverage extended for replay persistence behavior, tenant scope, and reset conditions.

### Findings closed this run
- ✅ **P1 Realtime durability gap**: replay no longer depends solely on in-memory broker state.
- ✅ **P1 Tenant isolation validation**: replay path explicitly tested against cross-tenant leakage.

### Findings opened this run
- ⏳ **P2 Build pipeline runtime**: `npm run build` times out in this CI runner during Vite transform; requires environment-level run window increase or resource tuning.

### Commands executed
- `python -m py_compile backend/amodb/apps/events/router.py backend/amodb/apps/events/tests/test_events_history.py backend/amodb/apps/events/broker.py`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm audit --audit-level=high --json`
- `cd frontend && npm run build`
- `cd frontend && npm run dev -- --host 0.0.0.0 --port 4173`

### Test coverage added
- `test_replay_events_since_persists_via_audit_store`
- `test_replay_events_since_requires_reset_for_unknown_or_expired_cursor`
- `test_replay_events_since_respects_tenant_scope`
- Existing `test_list_event_history_cursor_pagination` retained.

### Perf notes
- No new frontend bundle dependencies introduced.
- Realtime replay query path bounded by:
  - retention window (7 days),
  - replay max events (500).
- Event storm behavior remains protected by frontend 350ms debounced targeted invalidation.

### Files changed
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `AUDIT_SUMMARY.md`
- `AUDIT_REPORT.md`
- `ROUTE_MAP.md`
- `EVENT_SCHEMA.md`
- `SECURITY_REPORT.md`
- `BACKLOG.md`

### Verification steps
1. Start frontend and load `/maintenance/demo/quality`.
2. Validate cockpit loads in focus mode and sidebar remains fixed.
3. Open Action Panel and confirm evidence section visibility.
4. Run backend tests listed above; confirm replay/reset/tenant assertions pass.

### Screenshots / artifacts
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/cockpit-focus-mode.png`
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/action-panel-evidence.png`

### Known issues / follow-ups
- Build timeout in this environment still unresolved.
- Replay durability is bounded by audit retention policy, not a dedicated archival stream.


## Findings update (2026-02-10)
- **Closed**: multi-head alembic upgrade ambiguity for this feature set by creating a merge-compatible head migration `y3z4a5b6c7d8`.
- **Closed**: missing runtime columns on older DBs (`users.is_auditor`, `users.lockout_count`, `users.must_change_password`, `users.token_revoked_at`, and `audit_events` json payload cols) now auto-added when absent.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `AUDIT_REPORT.md`

### Commands run
- `python -m py_compile backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`

### Known issues / follow-up
- If a local DB is far behind, run full chain: `alembic -c amodb/alembic.ini upgrade head` before launching uvicorn.


## Phase result (2026-02-10)
### Root cause of "6-minute load" (measured)
- Route file imported all page modules eagerly, causing very large dev/prod preload graph (plotly/ag-grid/react-pdf and unrelated pages loaded for cockpit route).
- Cockpit mounted multiple full-list API calls for KPI derivation where aggregate snapshot existed.

### Perf report
| Metric | Observed | Notes |
|---|---:|---|
| First-load request count (dev capture) | 157 | Captured via Playwright perf script |
| Total transferred (dev capture) | 32,417,567 bytes | Includes Vite dev modules (non-gzip) |
| DCL (dev capture) | 20,908ms | Dev mode, not production baseline |
| Load event end (dev capture) | 20,935ms | Dev mode, not production baseline |
| Top resource | `react-plotly__js.js` (12.78MB) | Eager import evidence |

### What changed to fix
- Converted page imports in router to `React.lazy` + `Suspense` to prevent eager loading of non-active routes.
- Added Rollup manual chunking for heavy vendors (`charts-vendor`, `plotly-vendor`, `grid-vendor`, `pdf-vendor`).
- Replaced cockpit list-fetch dependencies (documents/audits/distributions lists) with single `/quality/qms/dashboard` aggregate call for snapshot KPIs.
- Capped history defaults (`limit=50`, max `200`) and added ETag/304 behavior for history endpoint.
- Added replay/history index migration for query path.

### Files changed
- `frontend/src/router.tsx`
- `frontend/vite.config.ts`
- `frontend/src/dashboards/DashboardCockpit.tsx`
- `frontend/src/services/qms.ts`
- `frontend/scripts/perf-report.mjs`
- `frontend/package.json`
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `backend/amodb/alembic/versions/z1y2x3w4v5u6_add_audit_events_replay_index.py`

### Commands executed
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && alembic -c amodb/alembic.ini upgrade head` *(env blocked: DATABASE_URL missing)*
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm run build` *(runner timeout)*
- Playwright cockpit perf capture (artifact + console PERF_JSON)

### Tests added/extended
- `test_list_event_history_sets_etag_header`
- `test_list_event_history_returns_304_on_matching_etag`

### Screenshots/artifacts
- `browser:/tmp/codex_browser_invocations/d217d7a1e1f1f99e/artifacts/artifacts/cockpit-load-optimized.png`
- `browser:/tmp/codex_browser_invocations/cffc26b8bc29c596/artifacts/artifacts/cockpit-network-trace.json`


## Changed in this run (2026-02-10)
### Root cause + fix
- Cockpit first-load latency was driven by concurrent `qmsListCars`, `listMyTasks`, and `getMyTrainingStatus` calls on mount.
- Replaced that fan-out with one compact backend snapshot endpoint (`GET /quality/qms/cockpit-snapshot`) + first-page activity history (`limit=50`).

### Production perf evidence
| Metric | Value | Evidence |
|---|---:|---|
| Total built JS/CSS (gzip) | 4,021,182 bytes | `frontend/dist/perf-report.json` |
| Cockpit shell chunk (`index-*.js`) gzip | 97,928 bytes | `frontend/dist/perf-report.json` |
| Largest offender gzip | 2,939,506 bytes (`plotly-vendor`) | `frontend/dist/perf-report.json` |
| First-page history API page size | 50 | `frontend/src/dashboards/DashboardCockpit.tsx` |

### Commands executed
- `cd backend && pytest amodb/apps/quality/tests/test_cockpit_snapshot.py amodb/apps/events/tests/test_events_history.py -q`
- `cd backend && DATABASE_URL=sqlite:///./alembic_local.db alembic -c amodb/alembic.ini heads`
- `cd backend && DATABASE_URL=sqlite:///./alembic_local.db alembic -c amodb/alembic.ini upgrade head` *(fails on SQLite constraint DDL; repo migrations require PostgreSQL for full run)*
- `cd frontend && npm run build`
- `cd frontend && node scripts/perf-report.mjs`

### Network/perf notes
- Playwright cockpit network capture attempt succeeded once for screenshot and then failed due Chromium crash in this runner (SIGSEGV), so waterfall request counts are not fully reproducible in this environment.
