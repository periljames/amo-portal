# REPO Verification Matrix

This matrix is generated from direct repository inspection. If an item is not evidenced in `portal_spec.md` or repo files, it is marked `UNKNOWN__FILL_ME`.

## Confirmed in repo/spec

| Area | Confirmed evidence | Why it matters |
|---|---|---|
| Backend framework | `backend/amodb/main.py` initializes FastAPI app and includes domain routers. | Confirms API runtime stack for deployment wiring. |
| Frontend framework | `frontend/package.json` uses Vite + React + TypeScript scripts (`dev`, `build`, `preview`). | Confirms SPA build/release flow. |
| Database + migrations | `backend/amodb/database.py` reads `DATABASE_WRITE_URL`/`DATABASE_URL`; Alembic tree exists under `backend/amodb/alembic`. | Confirms migration-based DB lifecycle. |
| Authentication model | `backend/amodb/security.py` uses JWT (`OAuth2PasswordBearer`, jose) and Argon2 hashing; `/auth/login` token URL configured. | Confirms auth primitive and secret requirements. |
| Health endpoints | `backend/amodb/main.py` exposes `/health`, `/healthz`, `/time`. | Enables deploy smoke checks and probes. |
| Streaming endpoint | `backend/amodb/apps/events/router.py` serves SSE under `/api/events` and `/api/events/history`; frontend consumes `/api/events` in `RealtimeProvider.tsx`. | Confirms stream route group and buffering needs. |
| Realtime broker integration | `backend/README.md` documents MQTT/WSS environment variables and broker expectations; `backend/amodb/apps/realtime/gateway.py` publishes via MQTT. | Confirms external broker dependency in production. |
| Upload traffic exists | Upload routes exist in manuals, reliability, quality, training, fleet routers (e.g. manuals `upload-docx`, reliability `ehm/logs/upload`). | Confirms need for explicit upload policy in edge proxy and capacity planning. |
| Existing NGINX guidance | `docs/nginx_realtime_snippet.conf` includes `/mqtt` websocket upgrade snippet. | Confirms websocket proxying is already in docs for broker path. |
| Multi-tenant indicators | Models/migrations include tenant/amo concepts (e.g., `add_multi_tenant_workflow_scaffold` migration; user `amo_id` usage in security/events paths). | Confirms tenant-aware backend behavior exists. |

## Missing / UNKNOWN__FILL_ME

| Area | Missing detail (required to finalize) | Current status |
|---|---|---|
| Product source-of-truth spec | `portal_spec.md` file is not present in repository. | `UNKNOWN__FILL_ME` |
| Tenant boundary requirements | Shared schema vs schema-per-tenant vs database-per-tenant, and any formal RLS policy. | `UNKNOWN__FILL_ME` |
| Explicit upload SLOs | Maximum upload size, peak concurrency, resumable/chunking requirement by endpoint. | `UNKNOWN__FILL_ME` |
| Streaming SLOs | Required session duration, reconnect policy target, expected event throughput. | `UNKNOWN__FILL_ME` |
| RPO/RTO + uptime goals | Backup and recovery objectives are not specified in repo docs. | `UNKNOWN__FILL_ME` |
| Production network details | VLAN/subnet IDs, firewall policy baseline, and DNS ownership are not in repo. | `UNKNOWN__FILL_ME` |
| Current deployment standard | No existing compose/systemd production deployment definition is present. | `UNKNOWN__FILL_ME` |
| CI/CD platform | No `.github/workflows`, `.gitlab-ci.yml`, or Jenkinsfile found. | `UNKNOWN__FILL_ME` |
| Secrets manager source | Vault/SOPS/1Password/etc. not declared. | `UNKNOWN__FILL_ME` |
| NAS protocol and mount contracts | NFS/SMB/object decision, mount points, and performance tiering not defined. | `UNKNOWN__FILL_ME` |
