# Complete Reliability Full-Stack Diagnostic

- Run: `30817716776`
- Source: `ca4f94365d9a90ee2626184238367c127a93516c`

| Stage | Exit code |
|---|---:|
| backend_patch | 0 |
| sod_patch | 0 |
| sod_escape | 0 |
| model_defaults | 0 |
| frontend_service | 0 |
| frontend_workspace | 0 |
| frontend_sod | 0 |
| frontend_css | 0 |
| py_compile | 0 |
| existing_upgrade | 1 |
| legacy_probe | 1 |
| migration_generate | 255 |
| migration_upgrade | 1 |
| migration_check | 255 |
| legacy_verify | 1 |
| migration_downgrade | 255 |
| migration_reupgrade | 1 |
| migration_recheck | 255 |
| app_import | 0 |
| backend_tests | 1 |
| governance | 1 |
| navigation | 0 |
| lint | 1 |
| build | 0 |

## Output tails

### backend_patch
```text
Canonical Reliability backend completion patch applied.
```

### sod_patch
```text
Reliability segregation-of-duties controls applied.
```

### sod_escape
```text
Generated Reliability approval newline corrected.
```

### model_defaults
```text
Applied migration-safe defaults.
```

### frontend_service
```text
Canonical Reliability service client completed.
```

### frontend_workspace
```text
Complete Reliability workspace, routes and navigation wired.
```

### frontend_sod
```text
Independent Reliability approvals wired to the frontend.
```

### frontend_css
```text
Complete Reliability workflow styles appended.
```

### py_compile
```text

```

### existing_upgrade
```text
INFO  [alembic.runtime.migration] Running upgrade  -> plat_p7_20260501, platform control plane tables and SaaS superadmin expansion
INFO  [alembic.runtime.migration] Running upgrade plat_p7_20260501 -> plat_20260627_support, tenant support sessions for platform read-only and approved admin access
INFO  [alembic.runtime.migration] Running upgrade plat_20260627_support -> qual_20260627_wf_close, close quality audit workflow gaps
INFO  [alembic.runtime.migration] Running upgrade b7d9f3a1c2e4 -> aa11bb22cc33, add training certificate issuance tables
INFO  [alembic.runtime.migration] Running upgrade qms_p2_20260426 -> qms_p3_20260501, global superuser tenant safety and QMS phase 3 hardening
INFO  [alembic.runtime.migration] Running upgrade qms_p3_20260501 -> qms_p4_20260501, phase 4 QMS route tree and workflow hardening
INFO  [alembic.runtime.migration] Running upgrade p0a6_train_record -> p0a7_train_record_dedupe, Deduplicate current training records and enforce one active record per user/course.
INFO  [alembic.runtime.migration] Running upgrade  -> qms_20260607_read_stability, QMS dashboard/calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade d7e6f5a4b3c2 -> m3a4n5u6l7s8, add manual audit log and ocr fields
INFO  [alembic.runtime.migration] Running upgrade m3a4n5u6l7s8 -> m4a5n6u7a8l9, add manual source storage fields and reader progress
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33, b2c3d4e5f6g7, c1d2e3f4a5b7, d7e6f5a4b3c2, p0a4_training_gate_fields -> c8d1e2f3a4b5, rename post-cutover legacy tables to *_legacy
INFO  [alembic.runtime.migration] Running upgrade c8d1e2f3a4b5 -> d9e2f3a4b5c6, hard drop post-cutover legacy tables after retention approval
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33 -> training_20260627_auditor_access, add training auditor access grants
INFO  [alembic.runtime.migration] Running upgrade training_20260627_auditor_access -> train_20260627_final, training final report settings and QR verification
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260704_scopes, add explicit audit scope management fields
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260627_scope, tenant audit scopes and scope-based QAR references
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_scope -> qual_20260628_scope_fix, Repair audit-scope columns after legacy scope migration.
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_scope_fix -> qual_20260628_lvl4, allow level 4 observation findings
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_lvl4 -> qual_20260704_schedfix, repair schedule frequency width and training report settings
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b1c2d3e4f5a6, b2c3d4e5f6g7, c1d2e3f4a5b7, c3d4e5f6a7b8, d0c1b2a3e4f5, d7e6f5a4b3c2, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, p0a4_training_gate_fields, s9t8u7v6w5x4, w2x3y4z5a6b7 -> u9v8w7x6y5z4, Add user groups.
INFO  [alembic.runtime.migration] Running upgrade u9v8w7x6y5z4 -> v0a1b2c3d4e5, ensure user group runtime columns exist
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> phase2_4_20260605, QMS calendar performance and training currency integrity indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_4_20260605 -> phase2_5_20260605, Restore QMS calendar performance and preserve canonical QMS styling support.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_notification_action_links, Add actionable QMS notification links.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/bin/alembic", line 6, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1023, in main
    self.run_cmd(cfg, options)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 957, in run_cmd
    fn(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 483, in upgrade
    script.run_env()
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 402, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 392, in run_migrations_online
    context.run_migrations()
  File "<string>", line 8, in run_migrations
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/environment.py", line 946, in run_migrations
    self.get_context().run_migrations(**kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 634, in run_migrations
    head_maintainer.update_to_step(step)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 866, in update_to_step
    self._update_version(from_, to_)
  File "/home/runner/work/amo-portal/amo-portal/backend/sitecustomize.py", line 134, in update_version_compat
    original_update(maintainer, from_, to_)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 801, in _update_version
    ret = self.context.impl._exec(
          ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/ddl/impl.py", line 246, in _exec
    return conn.execute(construct, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1419, in execute
    return meth(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2355, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.DataError: (psycopg2.errors.StringDataRightTruncation) value too long for type character varying(32)

[SQL: UPDATE alembic_version SET version_num='quality_20260705_notification_action_links' WHERE alembic_version.version_num = 'qual_20260704_schedfix']
(Background on this error at: https://sqlalche.me/e/20/9h9h)
```

### legacy_probe
```text
SET
ERROR:  relation "reliability_events" does not exist
LINE 1: SET session_replication_role=replica; INSERT INTO reliabilit...
                                                          ^
```

### migration_generate
```text
INFO  [alembic.runtime.migration] Running upgrade qms_p2_20260426 -> qms_p3_20260501, global superuser tenant safety and QMS phase 3 hardening
INFO  [alembic.runtime.migration] Running upgrade qms_p3_20260501 -> qms_p4_20260501, phase 4 QMS route tree and workflow hardening
INFO  [alembic.runtime.migration] Running upgrade p0a6_train_record -> p0a7_train_record_dedupe, Deduplicate current training records and enforce one active record per user/course.
INFO  [alembic.runtime.migration] Running upgrade  -> qms_20260607_read_stability, QMS dashboard/calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade d7e6f5a4b3c2 -> m3a4n5u6l7s8, add manual audit log and ocr fields
INFO  [alembic.runtime.migration] Running upgrade m3a4n5u6l7s8 -> m4a5n6u7a8l9, add manual source storage fields and reader progress
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33, b2c3d4e5f6g7, c1d2e3f4a5b7, d7e6f5a4b3c2, p0a4_training_gate_fields -> c8d1e2f3a4b5, rename post-cutover legacy tables to *_legacy
INFO  [alembic.runtime.migration] Running upgrade c8d1e2f3a4b5 -> d9e2f3a4b5c6, hard drop post-cutover legacy tables after retention approval
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33 -> training_20260627_auditor_access, add training auditor access grants
INFO  [alembic.runtime.migration] Running upgrade training_20260627_auditor_access -> train_20260627_final, training final report settings and QR verification
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260704_scopes, add explicit audit scope management fields
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260627_scope, tenant audit scopes and scope-based QAR references
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_scope -> qual_20260628_scope_fix, Repair audit-scope columns after legacy scope migration.
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_scope_fix -> qual_20260628_lvl4, allow level 4 observation findings
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_lvl4 -> qual_20260704_schedfix, repair schedule frequency width and training report settings
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b1c2d3e4f5a6, b2c3d4e5f6g7, c1d2e3f4a5b7, c3d4e5f6a7b8, d0c1b2a3e4f5, d7e6f5a4b3c2, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, p0a4_training_gate_fields, s9t8u7v6w5x4, w2x3y4z5a6b7 -> u9v8w7x6y5z4, Add user groups.
INFO  [alembic.runtime.migration] Running upgrade u9v8w7x6y5z4 -> v0a1b2c3d4e5, ensure user group runtime columns exist
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> phase2_4_20260605, QMS calendar performance and training currency integrity indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_4_20260605 -> phase2_5_20260605, Restore QMS calendar performance and preserve canonical QMS styling support.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_notification_action_links, Add actionable QMS notification links.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/bin/alembic", line 6, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1023, in main
    self.run_cmd(cfg, options)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 957, in run_cmd
    fn(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 483, in upgrade
    script.run_env()
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 402, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 392, in run_migrations_online
    context.run_migrations()
  File "<string>", line 8, in run_migrations
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/environment.py", line 946, in run_migrations
    self.get_context().run_migrations(**kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 634, in run_migrations
    head_maintainer.update_to_step(step)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 866, in update_to_step
    self._update_version(from_, to_)
  File "/home/runner/work/amo-portal/amo-portal/backend/sitecustomize.py", line 134, in update_version_compat
    original_update(maintainer, from_, to_)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 801, in _update_version
    ret = self.context.impl._exec(
          ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/ddl/impl.py", line 246, in _exec
    return conn.execute(construct, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1419, in execute
    return meth(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2355, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.DataError: (psycopg2.errors.StringDataRightTruncation) value too long for type character varying(32)

[SQL: UPDATE alembic_version SET version_num='quality_20260705_notification_action_links' WHERE alembic_version.version_num = 'qual_20260704_schedfix']
(Background on this error at: https://sqlalche.me/e/20/9h9h)
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
ERROR [alembic.util.messaging] Target database is not up to date.
FAILED: Target database is not up to date.
```

### migration_upgrade
```text
INFO  [alembic.runtime.migration] Running upgrade  -> plat_p7_20260501, platform control plane tables and SaaS superadmin expansion
INFO  [alembic.runtime.migration] Running upgrade plat_p7_20260501 -> plat_20260627_support, tenant support sessions for platform read-only and approved admin access
INFO  [alembic.runtime.migration] Running upgrade plat_20260627_support -> qual_20260627_wf_close, close quality audit workflow gaps
INFO  [alembic.runtime.migration] Running upgrade b7d9f3a1c2e4 -> aa11bb22cc33, add training certificate issuance tables
INFO  [alembic.runtime.migration] Running upgrade qms_p2_20260426 -> qms_p3_20260501, global superuser tenant safety and QMS phase 3 hardening
INFO  [alembic.runtime.migration] Running upgrade qms_p3_20260501 -> qms_p4_20260501, phase 4 QMS route tree and workflow hardening
INFO  [alembic.runtime.migration] Running upgrade p0a6_train_record -> p0a7_train_record_dedupe, Deduplicate current training records and enforce one active record per user/course.
INFO  [alembic.runtime.migration] Running upgrade  -> qms_20260607_read_stability, QMS dashboard/calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade d7e6f5a4b3c2 -> m3a4n5u6l7s8, add manual audit log and ocr fields
INFO  [alembic.runtime.migration] Running upgrade m3a4n5u6l7s8 -> m4a5n6u7a8l9, add manual source storage fields and reader progress
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33, b2c3d4e5f6g7, c1d2e3f4a5b7, d7e6f5a4b3c2, p0a4_training_gate_fields -> c8d1e2f3a4b5, rename post-cutover legacy tables to *_legacy
INFO  [alembic.runtime.migration] Running upgrade c8d1e2f3a4b5 -> d9e2f3a4b5c6, hard drop post-cutover legacy tables after retention approval
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33 -> training_20260627_auditor_access, add training auditor access grants
INFO  [alembic.runtime.migration] Running upgrade training_20260627_auditor_access -> train_20260627_final, training final report settings and QR verification
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260704_scopes, add explicit audit scope management fields
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260627_scope, tenant audit scopes and scope-based QAR references
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_scope -> qual_20260628_scope_fix, Repair audit-scope columns after legacy scope migration.
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_scope_fix -> qual_20260628_lvl4, allow level 4 observation findings
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_lvl4 -> qual_20260704_schedfix, repair schedule frequency width and training report settings
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b1c2d3e4f5a6, b2c3d4e5f6g7, c1d2e3f4a5b7, c3d4e5f6a7b8, d0c1b2a3e4f5, d7e6f5a4b3c2, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, p0a4_training_gate_fields, s9t8u7v6w5x4, w2x3y4z5a6b7 -> u9v8w7x6y5z4, Add user groups.
INFO  [alembic.runtime.migration] Running upgrade u9v8w7x6y5z4 -> v0a1b2c3d4e5, ensure user group runtime columns exist
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> phase2_4_20260605, QMS calendar performance and training currency integrity indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_4_20260605 -> phase2_5_20260605, Restore QMS calendar performance and preserve canonical QMS styling support.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_notification_action_links, Add actionable QMS notification links.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/bin/alembic", line 6, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1023, in main
    self.run_cmd(cfg, options)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 957, in run_cmd
    fn(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 483, in upgrade
    script.run_env()
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 402, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 392, in run_migrations_online
    context.run_migrations()
  File "<string>", line 8, in run_migrations
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/environment.py", line 946, in run_migrations
    self.get_context().run_migrations(**kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 634, in run_migrations
    head_maintainer.update_to_step(step)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 866, in update_to_step
    self._update_version(from_, to_)
  File "/home/runner/work/amo-portal/amo-portal/backend/sitecustomize.py", line 134, in update_version_compat
    original_update(maintainer, from_, to_)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 801, in _update_version
    ret = self.context.impl._exec(
          ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/ddl/impl.py", line 246, in _exec
    return conn.execute(construct, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1419, in execute
    return meth(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2355, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.DataError: (psycopg2.errors.StringDataRightTruncation) value too long for type character varying(32)

[SQL: UPDATE alembic_version SET version_num='quality_20260705_notification_action_links' WHERE alembic_version.version_num = 'qual_20260704_schedfix']
(Background on this error at: https://sqlalche.me/e/20/9h9h)
```

### migration_check
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
ERROR [alembic.util.messaging] Target database is not up to date.
FAILED: Target database is not up to date.
```

### legacy_verify
```text
ERROR:  relation "reliability_events" does not exist
LINE 1: ...n_status, validation_errors, provenance_json FROM reliabilit...
                                                             ^
```

### migration_downgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
ERROR [alembic.util.messaging] Relative revision -1 didn't produce 1 migrations
FAILED: Relative revision -1 didn't produce 1 migrations
```

### migration_reupgrade
```text
INFO  [alembic.runtime.migration] Running upgrade  -> plat_p7_20260501, platform control plane tables and SaaS superadmin expansion
INFO  [alembic.runtime.migration] Running upgrade plat_p7_20260501 -> plat_20260627_support, tenant support sessions for platform read-only and approved admin access
INFO  [alembic.runtime.migration] Running upgrade plat_20260627_support -> qual_20260627_wf_close, close quality audit workflow gaps
INFO  [alembic.runtime.migration] Running upgrade b7d9f3a1c2e4 -> aa11bb22cc33, add training certificate issuance tables
INFO  [alembic.runtime.migration] Running upgrade qms_p2_20260426 -> qms_p3_20260501, global superuser tenant safety and QMS phase 3 hardening
INFO  [alembic.runtime.migration] Running upgrade qms_p3_20260501 -> qms_p4_20260501, phase 4 QMS route tree and workflow hardening
INFO  [alembic.runtime.migration] Running upgrade p0a6_train_record -> p0a7_train_record_dedupe, Deduplicate current training records and enforce one active record per user/course.
INFO  [alembic.runtime.migration] Running upgrade  -> qms_20260607_read_stability, QMS dashboard/calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade d7e6f5a4b3c2 -> m3a4n5u6l7s8, add manual audit log and ocr fields
INFO  [alembic.runtime.migration] Running upgrade m3a4n5u6l7s8 -> m4a5n6u7a8l9, add manual source storage fields and reader progress
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33, b2c3d4e5f6g7, c1d2e3f4a5b7, d7e6f5a4b3c2, p0a4_training_gate_fields -> c8d1e2f3a4b5, rename post-cutover legacy tables to *_legacy
INFO  [alembic.runtime.migration] Running upgrade c8d1e2f3a4b5 -> d9e2f3a4b5c6, hard drop post-cutover legacy tables after retention approval
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33 -> training_20260627_auditor_access, add training auditor access grants
INFO  [alembic.runtime.migration] Running upgrade training_20260627_auditor_access -> train_20260627_final, training final report settings and QR verification
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260704_scopes, add explicit audit scope management fields
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260627_scope, tenant audit scopes and scope-based QAR references
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_scope -> qual_20260628_scope_fix, Repair audit-scope columns after legacy scope migration.
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_scope_fix -> qual_20260628_lvl4, allow level 4 observation findings
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_lvl4 -> qual_20260704_schedfix, repair schedule frequency width and training report settings
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b1c2d3e4f5a6, b2c3d4e5f6g7, c1d2e3f4a5b7, c3d4e5f6a7b8, d0c1b2a3e4f5, d7e6f5a4b3c2, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, p0a4_training_gate_fields, s9t8u7v6w5x4, w2x3y4z5a6b7 -> u9v8w7x6y5z4, Add user groups.
INFO  [alembic.runtime.migration] Running upgrade u9v8w7x6y5z4 -> v0a1b2c3d4e5, ensure user group runtime columns exist
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> phase2_4_20260605, QMS calendar performance and training currency integrity indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_4_20260605 -> phase2_5_20260605, Restore QMS calendar performance and preserve canonical QMS styling support.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_notification_action_links, Add actionable QMS notification links.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/bin/alembic", line 6, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1023, in main
    self.run_cmd(cfg, options)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 957, in run_cmd
    fn(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 483, in upgrade
    script.run_env()
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 402, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 392, in run_migrations_online
    context.run_migrations()
  File "<string>", line 8, in run_migrations
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/environment.py", line 946, in run_migrations
    self.get_context().run_migrations(**kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 634, in run_migrations
    head_maintainer.update_to_step(step)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 866, in update_to_step
    self._update_version(from_, to_)
  File "/home/runner/work/amo-portal/amo-portal/backend/sitecustomize.py", line 134, in update_version_compat
    original_update(maintainer, from_, to_)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 801, in _update_version
    ret = self.context.impl._exec(
          ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/ddl/impl.py", line 246, in _exec
    return conn.execute(construct, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1419, in execute
    return meth(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2355, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.DataError: (psycopg2.errors.StringDataRightTruncation) value too long for type character varying(32)

[SQL: UPDATE alembic_version SET version_num='quality_20260705_notification_action_links' WHERE alembic_version.version_num = 'qual_20260704_schedfix']
(Background on this error at: https://sqlalche.me/e/20/9h9h)
```

### migration_recheck
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
ERROR [alembic.util.messaging] Target database is not up to date.
FAILED: Target database is not up to date.
```

### app_import
```text
1132
```

### backend_tests
```text
amodb/apps/reliability/schemas.py:911
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:911: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityDefectRead(BaseModel):

amodb/apps/finance/schemas.py:21
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:21: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class CustomerRead(CustomerCreate):

amodb/apps/finance/schemas.py:39
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:39: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class VendorRead(VendorCreate):

amodb/apps/finance/schemas.py:54
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:54: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class GLAccountRead(GLAccountCreate):

amodb/apps/finance/schemas.py:82
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:82: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class InvoiceRead(BaseModel):

amodb/apps/finance/schemas.py:115
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:115: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class CreditNoteRead(BaseModel):

amodb/apps/finance/schemas.py:149
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:149: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class PaymentRead(BaseModel):

amodb/apps/finance/schemas.py:178
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:178: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class JournalRead(BaseModel):

amodb/apps/technical_records/schemas.py:28
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:28: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AircraftUtilisationRead(AircraftUtilisationCreate):

amodb/apps/technical_records/schemas.py:37
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:37: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ExceptionQueueItemRead(BaseModel):

amodb/apps/technical_records/schemas.py:55
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:55: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class DeferralRead(BaseModel):

amodb/apps/technical_records/schemas.py:70
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:70: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceRecordRead(BaseModel):

amodb/apps/technical_records/schemas.py:98
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:98: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AirworthinessItemRead(BaseModel):

amodb/apps/technical_records/schemas.py:122
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:122: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class TechnicalRecordSettingsRead(BaseModel):

amodb/apps/technical_records/schemas.py:153
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:153: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class WatchlistRead(WatchlistCreate):

amodb/apps/technical_records/schemas.py:209
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:209: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ComplianceActionRead(ComplianceActionCreate):

amodb/apps/technical_records/schemas.py:223
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:223: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ProductionExecutionEvidenceRead(BaseModel):

amodb/apps/technical_records/schemas.py:247
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:247: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ProductionReleaseGateRead(BaseModel):

amodb/apps/maintenance_program/schemas.py:101
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:101: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceProgramItemRead(MaintenanceProgramItemBase):

amodb/apps/maintenance_program/schemas.py:114
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:114: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceProgramItemSummary(BaseModel):

amodb/apps/maintenance_program/schemas.py:203
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:203: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AircraftProgramItemRead(AircraftProgramItemBase):

amodb/apps/reliability/tests/test_ehm.py: 2 warnings
amodb/apps/reliability/tests/test_notifications.py: 6 warnings
amodb/apps/reliability/tests/test_part_movements.py: 16 warnings
amodb/apps/reliability/tests/test_router.py: 2 warnings
  /opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py:3624: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    return util.wrap_callable(lambda ctx: fn(), fn)  # type: ignore

amodb/apps/reliability/tests/test_notifications.py::test_notifications_use_effective_amo_id
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/tests/test_notifications.py:102: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    created_at=datetime.utcnow(),

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED amodb/apps/reliability/tests/test_router.py::test_compute_trend_basic - assert 0 == 2
 +  where 0 = <ReliabilityDefectTrend id=1 aircraft=None window=2024-01-01:2024-01-31 rate=None>.defects_count
1 failed, 18 passed, 114 warnings in 1.09s
```

### governance
```text
ERROR:  relation "auth_capability_definitions" does not exist
LINE 1: SELECT (SELECT count(*) FROM auth_capability_definitions WHE...
                                     ^
```

### navigation
```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 8[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 9[2mms[22m[39m

[2m Test Files [22m [1m[32m2 passed[39m[22m[90m (2)[39m
[2m      Tests [22m [1m[32m8 passed[39m[22m[90m (8)[39m
[2m   Start at [22m 13:25:33
[2m   Duration [22m 365ms[2m (transform 330ms, setup 0ms, import 385ms, tests 17ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 60 stylesheets.
```

### lint
```text

/home/runner/work/amo-portal/amo-portal/frontend/src/pages/reliability/ReliabilityWorkspacePage.tsx
  63:17  error  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components  react-refresh/only-export-components

✖ 1 problem (1 error, 0 warnings)

```

### build
```text
[2mdist/[22m[2massets/[22m[36mQualityEnhancementsHost-BgUOcAkA.js             [39m[1m[2m    3.64 kB[22m[1m[22m[2m │ gzip:   1.78 kB[22m
[2mdist/[22m[2massets/[22m[36mPasswordResetPage-CMhWnVQ9.js                   [39m[1m[2m    3.77 kB[22m[1m[22m[2m │ gzip:   1.53 kB[22m
[2mdist/[22m[2massets/[22m[36mManualOverviewPage-BJW6Azaa.js                  [39m[1m[2m    4.00 kB[22m[1m[22m[2m │ gzip:   1.68 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformSecurityPage-BLvIi746.js                [39m[1m[2m    4.14 kB[22m[1m[22m[2m │ gzip:   1.42 kB[22m
[2mdist/[22m[2massets/[22m[36mpublications-DQ9T6GMY.js                        [39m[1m[2m    4.18 kB[22m[1m[22m[2m │ gzip:   1.75 kB[22m
[2mdist/[22m[2massets/[22m[36mrostering-DLSYKXAW.js                           [39m[1m[2m    4.30 kB[22m[1m[22m[2m │ gzip:   1.22 kB[22m
[2mdist/[22m[2massets/[22m[36mehm-DMCzSw3n.js                                 [39m[1m[2m    4.42 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoiceDetailPage-Cg-eUwYq.js              [39m[1m[2m    4.47 kB[22m[1m[22m[2m │ gzip:   1.59 kB[22m
[2mdist/[22m[2massets/[22m[36mVerifyScanPage-BrYLswTW.js                      [39m[1m[2m    4.55 kB[22m[1m[22m[2m │ gzip:   2.10 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoicesPage-gNWXXaJy.js                   [39m[1m[2m    4.58 kB[22m[1m[22m[2m │ gzip:   1.88 kB[22m
[2mdist/[22m[2massets/[22m[36mComplianceImpact-BhnReFnN.js                    [39m[1m[2m    4.86 kB[22m[1m[22m[2m │ gzip:   2.03 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkOrderDetailPage-B8WRy_sl.js      [39m[1m[2m    4.99 kB[22m[1m[22m[2m │ gzip:   1.77 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailLogsPage-C7flHcoA.js                       [39m[1m[2m    5.18 kB[22m[1m[22m[2m │ gzip:   2.15 kB[22m
[2mdist/[22m[2massets/[22m[36mManualWorkflowPage-I0kLp_i2.js                  [39m[1m[2m    5.25 kB[22m[1m[22m[2m │ gzip:   1.72 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterRuleQuickEditor-BFnnNiLR.js               [39m[1m[2m    5.62 kB[22m[1m[22m[2m │ gzip:   2.08 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityEvidenceViewerPage-CdoJMIvO.js           [39m[1m[2m    6.21 kB[22m[1m[22m[2m │ gzip:   2.58 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterDashboard-CrpZSY9D.js                     [39m[1m[2m    6.28 kB[22m[1m[22m[2m │ gzip:   2.14 kB[22m
[2mdist/[22m[2massets/[22m[36mTaskSummaryPage-B5cl4WA-.js                     [39m[1m[2m    6.42 kB[22m[1m[22m[2m │ gzip:   2.07 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmDashboardPage-D2q1ylV9.js                    [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.26 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterReports-CU5JepXk.js                       [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.34 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftDocumentsPage-BXtTx5e1.js               [39m[1m[2m    6.96 kB[22m[1m[22m[2m │ gzip:   2.45 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminOverviewPage-dhXZMZaz.js                   [39m[1m[2m    7.14 kB[22m[1m[22m[2m │ gzip:   2.74 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmUploadsPage-Bfy0b1GA.js                      [39m[1m[2m    7.46 kB[22m[1m[22m[2m │ gzip:   2.53 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderDetailPage-DumWw_8q.js                 [39m[1m[2m    7.47 kB[22m[1m[22m[2m │ gzip:   2.25 kB[22m
[2mdist/[22m[2massets/[22m[36madminUsers-Ba_PINaV.js                          [39m[1m[2m    7.70 kB[22m[1m[22m[2m │ gzip:   2.22 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRecycleBinPage-AQ3Dqjth.js          [39m[1m[2m    7.85 kB[22m[1m[22m[2m │ gzip:   2.32 kB[22m
[2mdist/[22m[2massets/[22m[36mCapacityBoard-84Mhwlv3.js                       [39m[1m[2m    7.95 kB[22m[1m[22m[2m │ gzip:   2.59 kB[22m
[2mdist/[22m[2massets/[22m[36mDutyLocationAssistant-CJP2_MLQ.js               [39m[1m[2m    8.24 kB[22m[1m[22m[2m │ gzip:   3.46 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRegisterPage-YO8o-rw2.js            [39m[1m[2m    8.66 kB[22m[1m[22m[2m │ gzip:   2.86 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentHomePage-DTXTs7DI.js                  [39m[1m[2m    8.80 kB[22m[1m[22m[2m │ gzip:   2.81 kB[22m
[2mdist/[22m[2massets/[22m[36mBrandProvider-CuSnutQZ.js                       [39m[1m[2m    9.02 kB[22m[1m[22m[2m │ gzip:   3.54 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterGovernancePanel-3pkZKmoH.js               [39m[1m[2m    9.23 kB[22m[1m[22m[2m │ gzip:   2.96 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoProfilePage-Bx8YUNzq.js                 [39m[1m[2m    9.42 kB[22m[1m[22m[2m │ gzip:   3.09 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderSearchPage-UCKl0d0v.js                 [39m[1m[2m    9.78 kB[22m[1m[22m[2m │ gzip:   2.76 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformTenantsPage-BLF0fo69.js                 [39m[1m[2m    9.82 kB[22m[1m[22m[2m │ gzip:   3.10 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsRegisterPage-CIpP7aCe.js                     [39m[1m[2m   10.14 kB[22m[1m[22m[2m │ gzip:   3.98 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformBillingPage-W8FkbJJk.js                 [39m[1m[2m   10.26 kB[22m[1m[22m[2m │ gzip:   2.93 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityChecklistPdfFormEditorHost-41CCey-5.js   [39m[1m[2m   11.10 kB[22m[1m[22m[2m │ gzip:   4.08 kB[22m
[2mdist/[22m[2massets/[22m[36mdocumentation-BJYgGv6s.js                       [39m[1m[2m   11.79 kB[22m[1m[22m[2m │ gzip:   4.08 kB[22m
[2mdist/[22m[2massets/[22m[36mUpsellPage-DQNcJB6M.js                          [39m[1m[2m   11.81 kB[22m[1m[22m[2m │ gzip:   4.51 kB[22m
[2mdist/[22m[2massets/[22m[36mUserProfilePage-DmfCm_qa.js                     [39m[1m[2m   12.60 kB[22m[1m[22m[2m │ gzip:   4.11 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmTrendsPage-sUajIwBx.js                       [39m[1m[2m   12.93 kB[22m[1m[22m[2m │ gzip:   5.04 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserNewPage-LbIfmLYx.js                    [39m[1m[2m   13.12 kB[22m[1m[22m[2m │ gzip:   4.15 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringPages-CXP4CApk.js                      [39m[1m[2m   13.23 kB[22m[1m[22m[2m │ gzip:   4.56 kB[22m
[2mdist/[22m[2massets/[22m[36mManualsDashboardPage-Cs-pykcF.js                [39m[1m[2m   13.30 kB[22m[1m[22m[2m │ gzip:   4.48 kB[22m
[2mdist/[22m[2massets/[22m[36mProductionWorkspacePage-BHZqPhbI.js             [39m[1m[2m   13.42 kB[22m[1m[22m[2m │ gzip:   3.84 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoManagementPage-Di5U7k4s.js              [39m[1m[2m   14.36 kB[22m[1m[22m[2m │ gzip:   4.37 kB[22m
[2mdist/[22m[2massets/[22m[36mtraining-CPwx-LRo.js                            [39m[1m[2m   16.04 kB[22m[1m[22m[2m │ gzip:   4.18 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditAssuranceDashboardPage-DJUBDPyB.js  [39m[1m[2m   16.73 kB[22m[1m[22m[2m │ gzip:   5.40 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUsageSettingsPage-BBDAYbFZ.js              [39m[1m[2m   17.25 kB[22m[1m[22m[2m │ gzip:   4.97 kB[22m
[2mdist/[22m[2massets/[22m[36mMyRosterWorkspace-kjw2xoKf.js                   [39m[1m[2m   18.54 kB[22m[1m[22m[2m │ gzip:   5.96 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformControlPage-Bcw6E6fm.js                 [39m[1m[2m   19.05 kB[22m[1m[22m[2m │ gzip:   5.58 kB[22m
[2mdist/[22m[2massets/[22m[36mLoginPage-DBtJpQGl.js                           [39m[1m[2m   22.07 kB[22m[1m[22m[2m │ gzip:   8.59 kB[22m
[2mdist/[22m[2massets/[22m[36mindex--wKoBmYi.js                               [39m[1m[2m   22.21 kB[22m[1m[22m[2m │ gzip:   6.20 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailServerSettingsPage-B9J63OUH.js             [39m[1m[2m   22.30 kB[22m[1m[22m[2m │ gzip:   7.01 kB[22m
[2mdist/[22m[2massets/[22m[36mqms-BpfVjVBe.js                                 [39m[1m[2m   22.45 kB[22m[1m[22m[2m │ gzip:   5.39 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterUi-XrJG1zZf.js                            [39m[1m[2m   23.24 kB[22m[1m[22m[2m │ gzip:   7.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserDetailPage-CccJGRJy.js                 [39m[1m[2m   23.95 kB[22m[1m[22m[2m │ gzip:   5.40 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditScheduleDetailPage-BOawiVh4.js      [39m[1m[2m   24.58 kB[22m[1m[22m[2m │ gzip:   7.62 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminDashboardPage-C6n5chV0.js                  [39m[1m[2m   25.77 kB[22m[1m[22m[2m │ gzip:   7.25 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-Czr2Gf7u.js                               [39m[1m[2m   26.77 kB[22m[1m[22m[2m │ gzip:   6.92 kB[22m
[2mdist/[22m[2massets/[22m[36mDashboardPage-CoBEGFdi.js                       [39m[1m[2m   28.09 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36musePlatformData-Dt_WDGi2.js                     [39m[1m[2m   28.69 kB[22m[1m[22m[2m │ gzip:   8.82 kB[22m
[2mdist/[22m[2massets/[22m[36mPlanningProductionPages-D3rYrp9z.js             [39m[1m[2m   29.07 kB[22m[1m[22m[2m │ gzip:   6.38 kB[22m
[2mdist/[22m[2massets/[22m[36mCRSNewPage-vJuLfPpU.js                          [39m[1m[2m   29.11 kB[22m[1m[22m[2m │ gzip:  10.90 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkforceHrWorkspace-CDWlrR6h.js                [39m[1m[2m   30.99 kB[22m[1m[22m[2m │ gzip:   7.60 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformIntegrationsPage-ztD072La.js            [39m[1m[2m   31.33 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36mUnifiedRosterPlanner-CXb6jPe8.js                [39m[1m[2m   33.52 kB[22m[1m[22m[2m │ gzip:  10.81 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringSetupWorkspace-5ewwBZBz.js             [39m[1m[2m   33.75 kB[22m[1m[22m[2m │ gzip:   9.18 kB[22m
[2mdist/[22m[2massets/[22m[36mSubscriptionManagementPage-BH1xZFeE.js          [39m[1m[2m   38.61 kB[22m[1m[22m[2m │ gzip:   9.52 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCarInvitePage-CkfXWaY7.js                 [39m[1m[2m   40.33 kB[22m[1m[22m[2m │ gzip:  11.36 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentLayout-CiQxbEui.js                    [39m[1m[2m   40.82 kB[22m[1m[22m[2m │ gzip:  12.67 kB[22m
[2mdist/[22m[2massets/[22m[36mTechnicalRecordsPages-CXqsfEIi.js               [39m[1m[2m   42.43 kB[22m[1m[22m[2m │ gzip:   9.22 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsOverviewPage-DgXbvNRW.js                     [39m[1m[2m   44.26 kB[22m[1m[22m[2m │ gzip:  12.41 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoAssetsPage-BOfTgHnM.js                  [39m[1m[2m   46.49 kB[22m[1m[22m[2m │ gzip:  12.81 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftImportPage-DkxdcvQ9.js                  [39m[1m[2m   48.31 kB[22m[1m[22m[2m │ gzip:  10.79 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSTrainingUserPage-C7lmvBHD.js                 [39m[1m[2m   49.09 kB[22m[1m[22m[2m │ gzip:  12.69 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityCarsPage-BOGGCjbj.js                     [39m[1m[2m   53.14 kB[22m[1m[22m[2m │ gzip:  12.99 kB[22m
[2mdist/[22m[2massets/[22m[36mMyTrainingPage-Cj4VLg4f.js                      [39m[1m[2m   55.37 kB[22m[1m[22m[2m │ gzip:  13.37 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsCanonicalPage-Dz770NNh.js                    [39m[1m[2m   61.48 kB[22m[1m[22m[2m │ gzip:  17.57 kB[22m
[2mdist/[22m[2massets/[22m[36mManualReaderPage-C9Ey97Rp.js                    [39m[1m[2m   62.51 kB[22m[1m[22m[2m │ gzip:  19.87 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditPlanSchedulePage-Ey61tqaE.js        [39m[1m[2m   68.00 kB[22m[1m[22m[2m │ gzip:  16.41 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRunHubPage-DF_Javkr.js              [39m[1m[2m   84.50 kB[22m[1m[22m[2m │ gzip:  23.21 kB[22m
[2mdist/[22m[2massets/[22m[36mReliabilityWorkspacePage-C10uS262.js            [39m[1m[2m   85.61 kB[22m[1m[22m[2m │ gzip:  18.59 kB[22m
[2mdist/[22m[2massets/[22m[36mTrainingCompetencePage-DqTk85MC.js              [39m[1m[2m   87.37 kB[22m[1m[22m[2m │ gzip:  18.72 kB[22m
[2mdist/[22m[2massets/[22m[36mproxy-C4MhIOBP.js                               [39m[1m[2m  122.34 kB[22m[1m[22m[2m │ gzip:  40.37 kB[22m
[2mdist/[22m[2massets/[22m[36mdocx-preview-DExmN-Pl.js                        [39m[1m[2m  172.23 kB[22m[1m[22m[2m │ gzip:  50.40 kB[22m
[2mdist/[22m[2massets/[22m[36mDocControlPages-DElRtcrj.js                     [39m[1m[2m  191.65 kB[22m[1m[22m[2m │ gzip:  42.73 kB[22m
[2mdist/[22m[2massets/[22m[36mmqtt.esm-sslCRx-_.js                            [39m[1m[2m  365.02 kB[22m[1m[22m[2m │ gzip: 110.45 kB[22m
[2mdist/[22m[2massets/[22m[36mgenerateCategoricalChart-DCtDYD9B.js            [39m[1m[2m  383.86 kB[22m[1m[22m[2m │ gzip: 105.91 kB[22m
[2mdist/[22m[2massets/[22m[36mEncoder-C1fvZ00O.js                             [39m[1m[2m  390.42 kB[22m[1m[22m[2m │ gzip: 102.86 kB[22m
[2mdist/[22m[2massets/[22m[36mpdf-vendor-pZBPlYZa.js                          [39m[1m[2m  422.68 kB[22m[1m[22m[2m │ gzip: 125.09 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-C45wi-pP.js                               [39m[1m[33m  509.23 kB[39m[22m[2m │ gzip: 142.35 kB[22m
[2mdist/[22m[2massets/[22m[36mgrid-vendor-CMBXYycc.js                         [39m[1m[33m  895.38 kB[39m[22m[2m │ gzip: 234.35 kB[22m
[33m
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.[39m
[32m✓ built in 13.96s[39m
```
