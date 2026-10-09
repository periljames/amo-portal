# Deferred verification obligations — Phase 10 only

1. Enumerate all Alembic heads after upstream merges; upgrade/downgrade against production-like PostgreSQL snapshots. Check composite FKs, unique constraints and reversible trigger removal.
2. Prove absent or mismatched `app.tenant_id` fails closed under FORCE RLS on every added table.
3. Confirm no cross-tenant contact/site/provider/contract/evidence/scope/guest user can be linked or queried.
4. Validate Quality supplier decisions and `assert_supplier_usage_allowed` for approval, hold, scope, expiry, suspended, revoked, and prospect states.
5. Verify descriptive metadata CRUD, stale version 409, validation and Quality-only consent/verification.
6. Verify real workbook supplier/contract mappings, XLSX/XLSM, formula strings, dates, missing values, invalid references, duplicates, concurrent uploads, dry-run, confirmation and CSV.
7. Verify idempotent fingerprint including mapping/sheet and controlled staging supersession/rollback. Ensure advanced Quality or operational records cannot be rolled back.
8. Verify frontend API integration, 403/409/422 messages, loading/edit/confirm buttons, focus and keyboard use.
9. Verify doc revision references and external account associations grant **zero** access until a later dedicated access phase.
10. Run deferred pytest, Vitest, Playwright, lint, typecheck, build and CI suites. Debug/repair defects in Phase 10, without weakening checks.
11. Reconcile with latest main and all related open PR changes before merge. Keep this PR draft until Phase 10.
