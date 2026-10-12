# Phase 1 implementation ledger

## Committed implementation
- [x] Reuse Procurement supplier as canonical tenant organization; no second Quality authority.
- [x] Add multi-role, site, contact, capability, authority/certificate, consented provider relationship, account association, Quality scope link and provenance structures.
- [x] Tenant-qualify provider/site/supplier/evidence, scope, parent, user and import relationships; add PostgreSQL FORCE RLS and reversible Alembic upgrade/downgrade.
- [x] Guard create/update by tenant identity and roles; optimistic row versions and Quality verification transitions.
- [x] Add provider profile administration frontend with role/site/contact/certification/governance views.
- [x] Stage XLSX/XLSM suppliers and contracts with mapped headers, worksheet selection, formulas, duplicates, supplier match and dates; no source Quality approval mutation.
- [x] Confirm inactive prospective suppliers; only an existing Quality approval transition can activate them. Quality Manager-only creation of contract DRAFT records.
- [x] Add source-file/row provenance, reconciliation CSV and staged supersession/guarded committed rollback.
- [x] Retain existing supplier use gate; inspect `service.assert_supplier_eligible` for status, holds and scope validity.
- [x] Inspect relevant real repository routes/models and indexed Draft MOPM Issue 4 excerpts.
- [x] Keep a single feature branch and draft PR; merge latest main.

## Source-dependent and deferred verification
- [ ] Exact vendor register and contracts tracker were not available. Source-specific header and contract column mapping **cannot be confirmed** without the real workbooks.
- [ ] Runtime migration upgrade/downgrade, full Alembic DAG-head comparison and production schema compatibility are Phase 10 verification obligations.
- [ ] Full API/browser access, route order and import reconciliation on real source workbooks remain unexecuted by Phase 1–9 policy.
- [ ] No test, lint, typecheck, build, benchmark or CI jobs were manually invoked during Phase 1. GitHub Actions did execute automatically for PR #560, exposing four migration failures; their fixes are committed but the newest CI run is not yet verified green.

Phase 1 code is committed; the source-dependent acceptance and testing are **not** claimed to pass.

## CI log-led remediation — 12 October 2026
- Reviewed the eight workflow runs attached to PR head `6341fa33ce020f90bd18af78322337022d57ebd5`. Four of eight had failed: Procurement Module (job `113824018731`), Document Control Lifecycle (job `113824023633`), QMS Live Audit Setup/Prepare (job `113824024575`), and Platform Control Plane (job `113824018552`). These four reports show the same first blocking migration error: `psycopg2.errors.DuplicateColumn` for `procurement_suppliers.external_import_pending_activation` at revision `extprov_261009_foundation`.
- Corrected the revision to add that column only when absent, preserving pre-existing bootstrap columns on downgrade. The revision marks newly created PostgreSQL columns for ownership-aware rollback. Repaired an invalid PL/pgSQL dollar-quote in the immutable event trigger function.
- Corrected `provider_identity_router.py`: removed an accidental self-recursive reference validator, installed actual create/PATCH reference checks, and resolved parent ownership from the saved relationship when updating contract or consent references in isolation.
- Corrected `ProviderImportPanel.tsx`: neutralizes spreadsheet-executable CSV cells and invalidates an earlier preview when source mapping, worksheet or header position changes. Corrected the imported-record message to reflect the staged batch kind.
- Corrected `ProviderIdentityPanel.tsx`: exposes site primary location and allows clearing nullable fields during controlled edits.
- No additional CI, migrations or test suites were manually launched as part of this remediation. These fixes address confirmed code defects; **green CI and 100% Phase 1 acceptance are not claimed.**
- The exact vendor register and Contracts & Agreements Tracker workbooks are still unverified. Source-specific import/header reconciliation remains an evidence dependency, not an assumed pass.

- Upstream reconciliation: current `main` commit `93537611f6edb50268d27875a1682587be6a7487` merged into PR #560 as `da15f94b342d9d2443f045980baa809e99a5d20e`. Comparison after merge confirmed 0 commits behind and exactly the same 15 Phase 1 file paths.
- Repaired import idempotency after failed transactions: restore transaction-local PostgreSQL tenant context before retry lookup; RLS otherwise hides the already-staged import.

## Subsequent CI evidence and static corrections — 12 October 2026
- On automatically triggered run `38210809642` (job `114684374516`), run `38210809633` (job `114684360891`), and run `38210809599` (job `114684307865`), clean PostgreSQL upgrade advanced past the duplicate-column failure and then reported `psycopg2.errors.DuplicateObject`: two foreign keys on `external_provider_relationships` used the generated name `fk_external_provider_relationships_amo_id_procurement_suppliers`. Corrected by giving the parent-provider tenant FK its own explicit name `fk_ext_provider_relationship_parent_supplier`.
- Platform Control Plane job `114684307638`, same automatic run, separately failed `test_broker_refresh_rate_is_independent_of_subscriber_count` (`health["refresh_count"] == calls`, observed 4 vs 5). The broker counted refreshes **after** its worker-thread await, allowing a health query to observe a completed callback that had not yet been counted. Moved successful completion accounting into the worker-call wrapper in `backend/amodb/apps/platform/ops_broker.py`. This is a genuine runtime correction, not a weakened assertion.
- Static review additionally corrected source-header mapping so empty worksheet headers cannot be auto-selected, added descriptive `SPECIALIZED_MAINTENANCE_PROVIDER` role end-to-end, and required the existing authorized Procurement/Stores/Quality edit roles to read administrative provider identities and import reviews.
- Changes remain limited to the original Phase 1 foundation plus the broker runtime module identified by CI. The PR remains a **single draft** targeting main; no new PR and no manual test runs.
- The downstream CI results after these patches have **not been confirmed green**. Keep the real source-workbook reconciliation and all Phase 10 checks open until verified.

- Subsequent clean PostgreSQL migration in automatic Platform Control Plane job `114686938906` failed on the immutable-event PL/pgSQL function (`psycopg2.errors.SyntaxError` at `AS $`). The branch still contained a single-dollar delimiter despite earlier intended correction. Replaced both SQL boundaries with PostgreSQL's valid tagged `$extprov$` delimiters; re-read commit `aedffae52fe57d3b23dac1648730f542d9014573` to confirm exactly those delimiters are stored. Repeat the complete migration in the deferred Phase 10 verification; no green claim from static inspection alone.
