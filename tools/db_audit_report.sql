-- Optional psql-only AMO Portal database audit report.
\pset pager off
\timing on
SELECT current_database() AS database_name, current_user AS current_user, version() AS postgres_version, now() AS captured_at;
SELECT version_num FROM alembic_version ORDER BY version_num;
SELECT n.nspname AS schema_name, c.relname AS table_name, c.relkind, pg_total_relation_size(c.oid) AS total_bytes, pg_relation_size(c.oid) AS table_bytes, pg_indexes_size(c.oid) AS index_bytes, COALESCE(s.n_live_tup, c.reltuples)::bigint AS estimated_rows, COALESCE(s.n_dead_tup, 0)::bigint AS estimated_dead_rows, s.seq_scan, s.seq_tup_read, s.idx_scan, s.last_autovacuum, s.last_autoanalyze FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND c.relkind IN ('r','p','m') ORDER BY pg_total_relation_size(c.oid) DESC;
SELECT table_schema, table_name, ordinal_position, column_name, data_type, udt_name, is_nullable, column_default FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name, ordinal_position;
SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename, indexname;
SELECT s.schemaname, s.relname AS table_name, s.indexrelname AS index_name, s.idx_scan, s.idx_tup_read, s.idx_tup_fetch, pg_relation_size(s.indexrelid) AS index_bytes FROM pg_stat_user_indexes s ORDER BY s.idx_scan ASC, pg_relation_size(s.indexrelid) DESC;
SELECT relname AS table_name, seq_scan, seq_tup_read, idx_scan, n_live_tup, n_dead_tup, pg_total_relation_size(relid) AS total_bytes FROM pg_stat_user_tables ORDER BY seq_tup_read DESC, seq_scan DESC;
