-- Venspera runtime database role: execute using a privileged migration role.
-- This script never creates or stores passwords. Set a strong runtime password
-- separately in your secret store and set DATABASE_WRITE_URL/DATABASE_URL for
-- API/worker processes to that role. DATABASE_MIGRATION_URL must be distinct.
-- Verify application-specific RLS policies before enabling paid tenant accounts.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'venspera_runtime') THEN
    CREATE ROLE venspera_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;

ALTER ROLE venspera_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
DO $
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO venspera_runtime', current_database());
END $;
GRANT USAGE ON SCHEMA public TO venspera_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO venspera_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO venspera_runtime;

-- This command is applied as the migration owner so future migrations inherit
-- DML grants. Reapply if another ownership role generates tables.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO venspera_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO venspera_runtime;

-- This service account has neither DDL permissions nor bypassrls by design.
-- Provision LOGIN and credentials outside source control once RLS has been
-- audited, e.g. via ALTER ROLE executed through a restricted DBA console.
-- PostgreSQL table owners bypass RLS unless FORCE is enabled; the runtime
-- account must NOT own tables.
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname = 'venspera_runtime';

-- Audit any public tenant-owned tables without RLS before go-live:
SELECT n.nspname AS schema_name, c.relname AS table_name,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
  AND c.relname LIKE 'tenant_%'
ORDER BY c.relname;
