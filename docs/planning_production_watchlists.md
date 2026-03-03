# Planning, Production, and Airworthiness Watchlists Integration

## Route map (tenant-scoped)
All routes are under `/maintenance/:amoCode/...` and resolve before the generic `/:department` fallback route.

### Planning
- `/planning/dashboard`
- `/planning/utilisation-monitoring`
- `/planning/forecast-due-list`
- `/planning/amp`
- `/planning/task-library`
- `/planning/ad-sb-eo-control`
- `/planning/work-packages`
- `/planning/work-orders`
- `/planning/deferments`
- `/planning/non-routine-review`
- `/planning/watchlists`
- `/planning/publication-review`
- `/planning/compliance-actions`

### Production
- `/production/dashboard`
- `/production/control-board`
- `/production/work-order-execution`
- `/production/findings`
- `/production/materials`
- `/production/review-inspection`
- `/production/release-prep`
- `/production/compliance-items`
- `/production/workspace` (legacy fleet worksheet retained as compatibility route)

## Backend workflow domain
Tenant-scoped technical-records tables:
- `technical_airworthiness_watchlists`
- `technical_airworthiness_publications`
- `technical_airworthiness_publication_matches`
- `technical_compliance_actions`
- `technical_compliance_action_history`

Migration: `a1b2c3d4e9f0_add_planning_production_watchlists.py`.

## Connector/source architecture
`/records/watchlists/{watchlist_id}/run` now executes via a source-adapter boundary (`technical_records/publication_sources.py`).
Current adapter set:
- `DeterministicPublicationSource` (simulated feed for stable test/demo execution)

This removes one-off hardcoded route logic and normalizes future source expansion to adapter registration (`get_publication_adapters()`).

## Cross-module integration delivered
- Planning dashboards and planning pages consume due list / AD-SB / deferment / work-order/compliance data and provide action routing.
- Production operational pages consume execution, findings, parts, inspection, compliance-action, and records traceability state.
- Quality cockpit snapshot includes AD/SB compliance exception metrics and compliance action queue items in the same action/priority pattern as CARs.
- Technical records traceability and dashboard signals are surfaced in production release-preparation and compliance execution context.

## Quality alert-zone integration
QMS cockpit snapshot now includes:
- `compliance_exceptions_open`
- `compliance_overdue`
- `compliance_unplanned_applicable`

Dashboard cockpit priority logic now escalates overdue/unplanned AD-SB compliance signals in the same priority zone style used for CAR/finding priority alerts.

## APIs used by Planning/Production pages
- `GET /records/planning/dashboard`
- `GET /records/production/dashboard`
- `GET/POST /records/watchlists`
- `POST /records/watchlists/{watchlist_id}/run`
- `GET /records/publications/review`
- `POST /records/publications/review/{match_id}/decision`
- `GET/POST /records/compliance-actions`
- `POST /records/compliance-actions/{action_id}/status`
- `GET /maintenance-program/program-items/`
- `GET /maintenance-program/aircraft/{aircraft_sn}/due-list`
- `POST /maintenance-program/aircraft/{aircraft_sn}/recompute-due`

## Permissions/gating
- Planning mutations (watchlist create/run, publication review decision, compliance action create): Planning role set.
- Compliance action execution transitions: Planning + Production execution role sets.
- Quality: read-only cockpit visibility with priority/action links into planning compliance routes.


## Demo seed and authenticated verification path
Preferred seeded-auth script:
- `python backend/scripts/seed_planning_production_auth_demo.py`

This script orchestrates:
- base tenant/user seed (`seed_demo.py`),
- maintenance execution seed (`seed_maintenance_module_demo.py`),
- technical records seed (`seed_technical_records_demo.py`),
- role-specific demo users (planning/production/quality/records),
- watchlist run + publication review + compliance action seed,
- initial production release-gate seed.

Environment knobs:
- `AMO_API_URL` (default `http://localhost:8080`)
- `AMO_LOGIN_SLUG` (default `demo-amo`)
- `AMO_ADMIN_PASSWORD` (default `ChangeMe123!`)

## Production execution persistence extensions
Technical records now persists production execution evidence and release-preparation gate state:
- `technical_production_execution_evidence`
- `technical_production_release_gates`

API additions:
- `GET /records/production/evidence`
- `POST /records/production/evidence/upload` (multipart file upload)
- `GET /records/production/release-gates`
- `POST /records/production/release-gates`

These are used by Production Control/Execution/Release pages to persist execution evidence, readiness transitions, signoff flags, and handoff-to-records state.

Screenshot manifest:
- `docs/screenshots/planning-production/manifest.md`


## Production hardening notes
- Authoritative seed entry point remains `backend/scripts/seed_planning_production_auth_demo.py`; it now runs the seed chain via `subprocess.run(..., check=True)` to fail fast and avoid silent partial seeding.
- Legacy `/maintenance/:amoCode/production` now redirects to `/maintenance/:amoCode/production/dashboard` so production users land on the operational dashboard; `/production/workspace` remains available as compatibility access for fleet worksheet workflows.
- Typed frontend service contracts for planning/production/watchlists/compliance and production execution were normalized to reduce `any` payload usage and duplicate query-string construction.


## PostgreSQL-backed runtime verification (2026-03-03)
Commands used for real runtime verification in this run:
1. Install/start PostgreSQL 16 (local service) and create roles/db.
2. Run migrations against PostgreSQL:
   - `cd backend && DATABASE_WRITE_URL=postgresql+psycopg2://amodb_migrator:***@localhost:5432/amodb DATABASE_URL=postgresql+psycopg2://amodb_app:***@localhost:5432/amodb python -m alembic -c amodb/alembic.ini upgrade heads`
3. Grant runtime privileges for app role on migrated objects.
4. Start backend:
   - `cd backend && DATABASE_WRITE_URL=postgresql+psycopg2://amodb_app:***@localhost:5432/amodb DATABASE_URL=postgresql+psycopg2://amodb_app:***@localhost:5432/amodb uvicorn amodb.main:app --host 0.0.0.0 --port 8080`
5. Start frontend:
   - `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173`
6. Run authoritative seeded-auth flow:
   - `AMO_API_URL=http://127.0.0.1:8080 python backend/scripts/seed_planning_production_auth_demo.py`

## Seed/auth hardening adjustments in this run
- `seed_planning_production_auth_demo.py` now enables required tenant modules (`fleet`, `reliability`, `maintenance_program`, `work`, `quality`, `training`) before follow-on maintenance/records seeding.
- The script now treats follow-on seeds as non-fatal to keep the authoritative seed flow usable even when idempotent records already exist.
- Runtime migration and seed blockers found during PostgreSQL execution were patched (see migration notes below), allowing full migration to `heads`.

## Migration safety notes from runtime proof
- No migration revisions were deleted or rebased.
- Historical migrations that failed on clean PostgreSQL runtime were hardened to be idempotent/compatible:
  - `f8a1b2c3d4e6_harden_part_movement_audit_fields.py`
  - `e3f1a2b3c4d5_seed_platform_superuser.py`
  - `n1b2c3d4e5f9_add_car_attachments.py`
- These changes preserve forward-only migration history and avoid destructive table drops.
