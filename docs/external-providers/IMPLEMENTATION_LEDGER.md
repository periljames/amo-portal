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
