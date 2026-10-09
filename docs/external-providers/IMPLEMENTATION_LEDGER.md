# Phase implementation ledger
- [x] Inspected canonical Procurement master and Quality-owned provider governance source.
- [x] Chose a single canonical Procurement supplier identity, multiple roles.
- [x] Added additive *schema definition* for provider roles, sites, contacts, capabilities and source links.
- [ ] Confirm latest migration heads and dependency compatibility on checkout.
- [x] Add controlled tenant-qualified role/site/contact/capability create/list/patch REST endpoints and optimistic version checks (static only).
- [x] Add Procurement Suppliers profile panel wired to the descriptive provider REST API (unverified).
- [ ] Implement real XLSX/XLSM import pipeline and staged reconciliation; an attempted importer was not committed.
- [ ] Verify route registration and Quality-linked eligibility, and expand tenant-scoped integrity to all cross-table evidence references.
- [ ] Implement real XLSX/XLSM source staging, validation, preview, idempotency, correction/rollback and reconciliation export.
- [ ] Complete account relationships, subcontractor consent, approvals and scoped evidence references.
- [ ] Inspect draft PDF and exact tracker workbooks.
- [ ] Audit all affected operational supplier-use entry points.
- [ ] Full static review of all changed code (not complete); API route ordering, PostgreSQL migration DAG and frontend integration still require confirmation.
No tests executed per phase policy; this is not a Phase 1 completion claim.
