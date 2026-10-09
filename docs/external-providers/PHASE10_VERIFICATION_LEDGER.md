# Phase 10 deferred verification ledger
1. Alembic: enumerate all revision heads, confirm single supported upgrade path and downgrade reversibility; inspect composite FK to supplier and associated uniqueness on production-like PostgreSQL.
2. PostgreSQL: cross-tenant FK rejection, forced RLS, absent/invalid `app.tenant_id`, privilege bypass checks, update/delete historical integrity.
3. QMS: approvals, suspensions, restrictions, evaluations and contract gate through all Procurement operational paths, including dispatch and receipt.
4. API: create/update/read authorization, site/contact foreign-key tenant enforcement, 409 stale versions and missing parents.
5. Import: XLSX/XLSM macro stripping, missing/formula/date/duplicate validation, preview, idempotent commit, rollback and reconciliation exports with real trackers.
6. UI: CRUD persistence, confirmation/error states, keyboard controls, duplicate handling, tenant segregation.
7. CI/test suites: pytest, Playwright, Vitest, lint, typecheck and builds all deferred until Phase 10.
8. Verify all known open PR interference and main updates before final Phase 10 merge.
\n9. Verify exact contract-tracker schema; prove no contract row is accidentally treated as an approvable supplier; implement missing contract reconciliation before Phase 1 signoff.\n10. Verify repeated-file idempotency and concurrency conflicts; confirm all import batches and row records remain tenant-isolated.\n