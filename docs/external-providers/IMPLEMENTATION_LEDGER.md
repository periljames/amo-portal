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
- [ ] No pytest, Vitest, Playwright, lint, typecheck, builds, CI, or benchmark runs performed.

Phase 1 code is committed; the source-dependent acceptance and testing are **not** claimed to pass.

## CI log-led remediation — 12 October 2026
- Reviewed the eight workflow runs attached to PR head `6341fa33ce020f90bd18af78322337022d57ebd5`. Four of eight had failed: Procurement Module (job `113824018731`), Document Control Lifecycle (job `113824023633`), QMS Live Audit Setup/Prepare (job `113824024575`), and Platform Control Plane (job `113824018552`). These four reports show the same first blocking migration error: `psycopg2.errors.DuplicateColumn` for `procurement_suppliers.external_import_pending_activation` at revision `extprov_261009_foundation`.
- Corrected the revision to add that column only when absent, preserving pre-existing bootstrap columns on downgrade. The revision marks newly created PostgreSQL columns for ownership-aware rollback. Repaired an invalid PL/pgSQL dollar-quote in the immutable event trigger function.
- Corrected `provider_identity_router.py`: removed an accidental self-recursive reference validator, installed actual create/PATCH reference checks, and resolved parent ownership from the saved relationship when updating contract or consent references in isolation.
- Corrected `ProviderImportPanel.tsx`: neutralizes spreadsheet-executable CSV cells and invalidates an earlier preview when source mapping, worksheet or header position changes. Corrected the imported-record message to reflect the staged batch kind.
- Corrected `ProviderIdentityPanel.tsx`: exposes site primary location and allows clearing nullable fields during controlled edits.
- No additional CI, migrations or test suites were manually launched as part of this remediation. These fixes address confirmed code defects; **green CI and 100% Phase 1 acceptance are not claimed.**
- The exact vendor register and Contracts & Agreements Tracker workbooks are still unverified. Source-specific import/header reconciliation remains an evidence dependency, not an assumed pass.
