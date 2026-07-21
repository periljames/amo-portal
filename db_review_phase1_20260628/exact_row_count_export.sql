-- Exact row-count and safe stale-table validation export.
-- This is read-only. It does not export row contents.
\pset pager off
\timing on

DO $$
DECLARE
    r record;
    v_count bigint;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS tmp_table_counts (
        schema_name text,
        table_name text,
        exact_count bigint,
        captured_at timestamptz default now()
    ) ON COMMIT PRESERVE ROWS;
    TRUNCATE tmp_table_counts;

    FOR r IN
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    LOOP
        EXECUTE format('SELECT count(*) FROM %I.%I', r.table_schema, r.table_name) INTO v_count;
        INSERT INTO tmp_table_counts(schema_name, table_name, exact_count)
        VALUES (r.table_schema, r.table_name, v_count);
    END LOOP;
END $$;

SELECT * FROM tmp_table_counts ORDER BY exact_count DESC, table_name;

-- Helpful after schema changes, but run manually during a maintenance window if DB is large:
-- ANALYZE;