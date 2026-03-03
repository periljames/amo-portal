# Planning/Production Authenticated Screenshot Manifest

## Run context
- Intended tenant slug: `demo-amo`
- Intended seeded users:
  - `planner@demo.example.com`
  - `production@demo.example.com`
  - `quality@demo.example.com`

## Authoritative seeding script
- `python backend/scripts/seed_planning_production_auth_demo.py` (runs base + maintenance + technical records seeds and role user provisioning)

## Attempted setup commands
1. `cd backend && export DATABASE_WRITE_URL=sqlite+pysqlite:///./dev.db && export DATABASE_URL=$DATABASE_WRITE_URL && python -m alembic -c amodb/alembic.ini upgrade heads`
2. `cd backend && export DATABASE_WRITE_URL=sqlite+pysqlite:///./dev.db && export SCHEMA_STRICT=0 && python - <<'PY' ... Base.metadata.create_all ... PY`
3. `python backend/scripts/seed_planning_production_auth_demo.py`

## Result
Authenticated seeded screenshot capture is currently **blocked in this container** because the repository migrations/models require PostgreSQL-specific features (`JSONB`, alter-constraint operations) and a local PostgreSQL runtime is unavailable in this execution environment.

- SQLite migration path fails (`NotImplementedError` for ALTER CONSTRAINT and JSONB type compilation).
- Docker is unavailable in this container (`docker: command not found`), so a local PostgreSQL service could not be provisioned for full seeded auth flow.

## Proof status
No login-page-only screenshots were recorded as evidence of completed module pages.
