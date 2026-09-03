-- Extensions required by AMO Portal migrations.
-- Runs once, as the Postgres superuser, on first initialisation of the bundled
-- database volume. Safe to re-run (IF NOT EXISTS).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;
