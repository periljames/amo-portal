# Hidden-Writer Audit Checklist

## Objective
Ensure no legacy/duplicate tables are still being written outside approved cutover paths.

## 1) API routes
- [ ] Enumerate route handlers touching candidate models/tables.
- [ ] Confirm create/update/delete paths are feature-flag aware.
- [ ] Confirm no direct SQL writes bypassing service layer.
- [ ] Verify bulk endpoints and admin-only endpoints.

## 2) Services
- [ ] Search for ORM writes (`add`, `merge`, `delete`, `execute` with INSERT/UPDATE/DELETE).
- [ ] Confirm service methods for legacy tables are either read-only or dual-write wrapped.
- [ ] Verify idempotency and retry behavior does not create divergence.

## 3) Background jobs / schedulers
- [ ] Inventory cron/Celery/RQ/APScheduler jobs writing candidate tables.
- [ ] Confirm job write targets after cutover flag activation.
- [ ] Validate replay/retry jobs do not backfill legacy-only paths.

## 4) Scripts and CLI tools
- [ ] Audit `backend/scripts` and `amodb/scripts` for direct table writes.
- [ ] Confirm data-fix scripts use canonical target tables.
- [ ] Mark any script requiring deprecation or guardrail banner.

## 5) Imports / ETL loaders
- [ ] Validate import pipelines for aircraft utilization and maintenance templates.
- [ ] Ensure import reconciliation targets canonical tables after cutover.
- [ ] Verify staging tables do not write into legacy entities post-cutover.

## 6) Integrations
- [ ] Audit outbound/inbound integration handlers that map into candidate tables.
- [ ] Confirm webhook processors and external sync jobs are feature-flag gated.
- [ ] Confirm failure/retry queues preserve canonical write target.

## 7) Tests / fixtures
- [ ] Identify tests still inserting into legacy tables or legacy mappers.
- [ ] Update fixtures to canonical tables while keeping backward-compat tests explicit.
- [ ] Separate migration-compat tests from canonical behavior tests.

## 8) Evidence capture per finding
For each hidden writer discovered, record:
- Location (file + function)
- Write target table/model
- Execution path (route/job/script/integration/test)
- Flag coverage (yes/no)
- Risk rating (high/med/low)
- Remediation owner + due date

## 9) Completion gate
- [ ] No unmanaged writers to legacy tables remain in active runtime paths.
- [ ] All exceptions approved and time-boxed with remediation tickets.
