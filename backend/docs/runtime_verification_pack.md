# Runtime Verification Pack (Staging/Production)

> Scope is limited to existing approved candidates only:
> 1) users mapper duplication, 2) maintenance program consolidation,
> 3) utilization consolidation, 4) corrective-action consolidation.

## 0) Operator instructions
- Run in **staging first**, then production.
- Use read-only DB credentials where possible.
- Capture outputs to timestamped artifacts for sign-off.

```sql
-- recommended psql session settings
\timing on
\pset pager off
\set ON_ERROR_STOP on
```

---

## 1) Global schema inspections (exact SQL)

### 1.1 Table existence
```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'users','maintenance_program_items','maintenance_statuses','amp_program_items','aircraft_program_items',
    'aircraft_usage','technical_aircraft_utilisation','aircraft_utilization_daily',
    'qms_corrective_actions','quality_cars','quality_car_actions','quality_car_responses','quality_car_attachments',
    'qms_notifications','training_notifications','reliability_notifications'
  )
ORDER BY table_name;
```

### 1.2 Columns, data types, nullability, defaults
```sql
SELECT table_name, ordinal_position, column_name, data_type, udt_name,
       is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'users','maintenance_program_items','maintenance_statuses','amp_program_items','aircraft_program_items',
    'aircraft_usage','technical_aircraft_utilisation','aircraft_utilization_daily',
    'qms_corrective_actions','quality_cars','qms_notifications','training_notifications','reliability_notifications'
  )
ORDER BY table_name, ordinal_position;
```

### 1.3 Indexes
```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'users','maintenance_program_items','maintenance_statuses','amp_program_items','aircraft_program_items',
    'aircraft_usage','technical_aircraft_utilisation','aircraft_utilization_daily',
    'qms_corrective_actions','quality_cars','qms_notifications','training_notifications','reliability_notifications'
  )
ORDER BY tablename, indexname;
```

### 1.4 Uniques and PKs
```sql
SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
       string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN (
    'users','maintenance_program_items','maintenance_statuses','amp_program_items','aircraft_program_items',
    'aircraft_usage','technical_aircraft_utilisation','aircraft_utilization_daily',
    'qms_corrective_actions','quality_cars','qms_notifications','training_notifications','reliability_notifications'
  )
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;
```

### 1.5 Foreign keys
```sql
SELECT tc.table_name,
       tc.constraint_name,
       kcu.column_name,
       ccu.table_name AS referenced_table,
       ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.table_schema = tc.table_schema
WHERE tc.table_schema = 'public'
  AND tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN (
    'users','maintenance_program_items','maintenance_statuses','amp_program_items','aircraft_program_items',
    'aircraft_usage','technical_aircraft_utilisation','aircraft_utilization_daily',
    'qms_corrective_actions','quality_cars','qms_notifications','training_notifications','reliability_notifications'
  )
ORDER BY tc.table_name, tc.constraint_name;
```

### 1.6 Row counts by AMO (or global when no `amo_id`)
```sql
-- replace with exact table set as needed
SELECT 'users' AS table_name, amo_id, COUNT(*) FROM users GROUP BY amo_id
UNION ALL
SELECT 'amp_program_items', NULL::text, COUNT(*) FROM amp_program_items
UNION ALL
SELECT 'aircraft_program_items', NULL::text, COUNT(*) FROM aircraft_program_items
UNION ALL
SELECT 'maintenance_program_items', NULL::text, COUNT(*) FROM maintenance_program_items
UNION ALL
SELECT 'maintenance_statuses', NULL::text, COUNT(*) FROM maintenance_statuses
UNION ALL
SELECT 'aircraft_usage', amo_id, COUNT(*) FROM aircraft_usage GROUP BY amo_id
UNION ALL
SELECT 'technical_aircraft_utilisation', amo_id, COUNT(*) FROM technical_aircraft_utilisation GROUP BY amo_id
UNION ALL
SELECT 'aircraft_utilization_daily', amo_id, COUNT(*) FROM aircraft_utilization_daily GROUP BY amo_id
UNION ALL
SELECT 'qms_corrective_actions', NULL::text, COUNT(*) FROM qms_corrective_actions
UNION ALL
SELECT 'quality_cars', amo_id, COUNT(*) FROM quality_cars GROUP BY amo_id
UNION ALL
SELECT 'qms_notifications', amo_id, COUNT(*) FROM qms_notifications GROUP BY amo_id
UNION ALL
SELECT 'training_notifications', amo_id, COUNT(*) FROM training_notifications GROUP BY amo_id
UNION ALL
SELECT 'reliability_notifications', amo_id, COUNT(*) FROM reliability_notifications GROUP BY amo_id;
```

---

## 2) Candidate reconciliation SQL

## 2.1 Users mapper duplication (`users` canonical, legacy mapper contract parity)
```sql
-- legacy-contract fields available?
SELECT
  COUNT(*) FILTER (WHERE user_code IS NULL) AS null_user_code,
  COUNT(*) FILTER (WHERE staff_code IS NULL) AS null_staff_code,
  COUNT(*) FILTER (WHERE amo_id IS NULL) AS null_amo_id,
  COUNT(*) FILTER (WHERE department_id IS NULL) AS null_department_id
FROM users;
```

```sql
-- amo_code compatibility derivation parity (if amo_code legacy snapshot table/column exists in workloads)
SELECT u.id, u.amo_id, a.amo_code
FROM users u
LEFT JOIN amos a ON a.id = u.amo_id
WHERE u.amo_id IS NOT NULL
LIMIT 200;
```

```sql
-- duplicate risk checks for canonical business keys
SELECT amo_id, email, COUNT(*)
FROM users
GROUP BY amo_id, email
HAVING COUNT(*) > 1;
```

## 2.2 Maintenance program (`maintenance_*` vs `amp_*`)
```sql
-- template-level overlap by task identity
SELECT mpi.aircraft_template, mpi.ata_chapter, mpi.task_code,
       COUNT(*) AS legacy_rows,
       COUNT(api.id) AS canonical_matches
FROM maintenance_program_items mpi
LEFT JOIN amp_program_items api
  ON api.template_code = mpi.aircraft_template
 AND api.ata_chapter = mpi.ata_chapter
 AND api.task_code = mpi.task_code
GROUP BY mpi.aircraft_template, mpi.ata_chapter, mpi.task_code
HAVING COUNT(api.id) = 0;
```

```sql
-- status-level overlap (legacy maintenance_statuses -> aircraft_program_items)
SELECT ms.aircraft_serial_number, ms.program_item_id,
       COUNT(*) AS legacy_count,
       COUNT(api.id) AS canonical_count
FROM maintenance_statuses ms
LEFT JOIN maintenance_program_items mpi ON mpi.id = ms.program_item_id
LEFT JOIN amp_program_items ap ON ap.template_code = mpi.aircraft_template
                             AND ap.ata_chapter = mpi.ata_chapter
                             AND ap.task_code = mpi.task_code
LEFT JOIN aircraft_program_items api
       ON api.aircraft_serial_number = ms.aircraft_serial_number
      AND api.program_item_id = ap.id
GROUP BY ms.aircraft_serial_number, ms.program_item_id
HAVING COUNT(api.id) = 0;
```

## 2.3 Utilization (`aircraft_usage` vs `technical_aircraft_utilisation` vs `aircraft_utilization_daily`)
```sql
-- raw-to-raw parity by AMO/aircraft/day
WITH au AS (
  SELECT amo_id, aircraft_serial_number, date AS d,
         SUM(block_hours)::numeric(18,4) AS hrs,
         SUM(cycles)::numeric(18,4) AS cyc
  FROM aircraft_usage
  GROUP BY amo_id, aircraft_serial_number, date
), tu AS (
  SELECT amo_id, aircraft_serial_number, entry_date AS d,
         SUM(hours)::numeric(18,4) AS hrs,
         SUM(cycles)::numeric(18,4) AS cyc
  FROM technical_aircraft_utilisation
  GROUP BY amo_id, aircraft_serial_number, entry_date
)
SELECT COALESCE(au.amo_id, tu.amo_id) AS amo_id,
       COALESCE(au.aircraft_serial_number, tu.aircraft_serial_number) AS aircraft_serial_number,
       COALESCE(au.d, tu.d) AS day,
       au.hrs AS au_hrs, tu.hrs AS tu_hrs,
       au.cyc AS au_cyc, tu.cyc AS tu_cyc
FROM au
FULL OUTER JOIN tu
  ON au.amo_id = tu.amo_id
 AND au.aircraft_serial_number = tu.aircraft_serial_number
 AND au.d = tu.d
WHERE COALESCE(au.hrs,0) <> COALESCE(tu.hrs,0)
   OR COALESCE(au.cyc,0) <> COALESCE(tu.cyc,0)
ORDER BY 1,2,3;
```

```sql
-- derived parity check against daily table
WITH au AS (
  SELECT amo_id, aircraft_serial_number, date AS d,
         SUM(block_hours)::numeric(18,4) AS hrs,
         SUM(cycles)::numeric(18,4) AS cyc
  FROM aircraft_usage
  GROUP BY amo_id, aircraft_serial_number, date
)
SELECT au.amo_id, au.aircraft_serial_number, au.d,
       au.hrs AS raw_hrs, ad.hours AS daily_hrs,
       au.cyc AS raw_cyc, ad.cycles AS daily_cyc
FROM au
LEFT JOIN aircraft_utilization_daily ad
  ON ad.amo_id = au.amo_id
 AND ad.aircraft_serial_number = au.aircraft_serial_number
 AND ad.date = au.d
WHERE ad.id IS NULL
   OR COALESCE(au.hrs,0) <> COALESCE(ad.hours,0)
   OR COALESCE(au.cyc,0) <> COALESCE(ad.cycles,0)
ORDER BY 1,2,3;
```

## 2.4 Corrective actions (`qms_corrective_actions` -> `quality_cars`)
```sql
-- CAP records with no corresponding CAR by finding_id
SELECT cap.finding_id, COUNT(*) AS cap_rows
FROM qms_corrective_actions cap
LEFT JOIN quality_cars car ON car.finding_id = cap.finding_id
GROUP BY cap.finding_id
HAVING COUNT(car.id) = 0;
```

```sql
-- key field parity sample (status/due/responsible)
SELECT cap.id AS cap_id, cap.finding_id,
       cap.status AS cap_status, car.status AS car_status,
       cap.due_date AS cap_due_date, car.due_date AS car_due_date,
       cap.responsible_user_id AS cap_owner, car.assigned_to_user_id AS car_owner
FROM qms_corrective_actions cap
JOIN quality_cars car ON car.finding_id = cap.finding_id
WHERE cap.status::text <> car.status::text
   OR COALESCE(cap.due_date, DATE '1900-01-01') <> COALESCE(car.due_date, DATE '1900-01-01')
   OR COALESCE(cap.responsible_user_id::text, '') <> COALESCE(car.assigned_to_user_id::text, '')
ORDER BY cap.finding_id;
```

---

## 3) Drift-detection SQL

### 3.1 Orphan FK detectors (examples)
```sql
-- aircraft_program_items.program_item_id orphan check
SELECT api.id
FROM aircraft_program_items api
LEFT JOIN amp_program_items ap ON ap.id = api.program_item_id
WHERE ap.id IS NULL;
```

```sql
-- quality_cars.finding_id orphan check
SELECT car.id, car.finding_id
FROM quality_cars car
LEFT JOIN qms_audit_findings f ON f.id = car.finding_id
WHERE car.finding_id IS NOT NULL AND f.id IS NULL;
```

### 3.2 Duplicate business keys
```sql
-- canonical user uniqueness drift
SELECT amo_id, email, COUNT(*)
FROM users
GROUP BY amo_id, email
HAVING COUNT(*) > 1;
```

```sql
-- legacy maintenance template duplicates
SELECT aircraft_template, ata_chapter, task_code, COUNT(*)
FROM maintenance_program_items
GROUP BY aircraft_template, ata_chapter, task_code
HAVING COUNT(*) > 1;
```

### 3.3 Enum drift (status values not in approved mapping)
```sql
-- adjust approved sets to your runtime policy before use
SELECT status::text, COUNT(*)
FROM qms_corrective_actions
GROUP BY status::text
ORDER BY COUNT(*) DESC;

SELECT status::text, COUNT(*)
FROM quality_cars
GROUP BY status::text
ORDER BY COUNT(*) DESC;
```

### 3.4 Nullability violations for required cutover fields
```sql
SELECT
  COUNT(*) FILTER (WHERE amo_id IS NULL) AS users_null_amo_id,
  COUNT(*) FILTER (WHERE email IS NULL) AS users_null_email
FROM users;

SELECT
  COUNT(*) FILTER (WHERE aircraft_serial_number IS NULL) AS api_null_aircraft,
  COUNT(*) FILTER (WHERE program_item_id IS NULL) AS api_null_program
FROM aircraft_program_items;
```

---

## 4) Sign-off criteria
- All candidate reconciliation query result sets must be empty or explicitly waived.
- Drift detectors must be zero (or have approved exceptions with ticket IDs).
- Baseline snapshots stored for rollback comparison.
