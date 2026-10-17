
# Phase 6 — Supplier Procurement Collaboration and Parts Requisitions

**PR #560, same branch: codex/external-provider-platform-20261009. Source implemented; not runtime accepted. No Phase 7.**

## System boundaries

**Procurement** retains requisition, technical and budget approvals, sourcing, approved provider selection, RFQs, canonical quotations and evaluation, PO approval and issuance. External submissions never award a quote or approve an internal PO. The authorized staff Sourcing, Orders and Receiving pages remain unchanged in ownership.

**QMS** controls supplier status, category/site/scope/date eligibility, active holds, restrictions, qualification and any mandatory executed maintenance contract. New transactions recheck these live, without reliance on client cache or PO override.

**DMS** controls classified originals, published revision downloads, document ownership, retention, legal hold and disposal. The external upload surface reuses Phase 5 bounded/scanned/hash-checked/resumable storage and DCO-only evidence registration, now with RFQ, issued PO and ASN links. Internal Procurement records an original by reference, not an uncontrolled copy; QMS evidence verification remains separate.

**Stores/Quality** alone receive, quarantine, inspect and release material. Advance Shipment Notices never change physical receipt or serviceability. **Finance** exclusively performs matching, banking and payments. Providers see only permitted invoice matching status and may submit an invoice notice linked to an accepted DMS-retained original.

## Operational paths implemented in source

1. The migration external_providers_20261016_procurement.py extends Phase 5 evidence scopes and creates tenant-isolated provider quotation revision links, supplier advance-shipment notices and append-only attributable transaction events. Each received revision refers to an existing canonical ProcurementQuote, not a new approval engine.
2. The external commerce API under /api/external-provider/partner/{tenant_slug}/commerce exposes ONLY assigned issued RFQs, safe requisition-line specs (never budget/approval data), member-granted current DMS original downloads, acknowledgments, multi-line quotations, currency, freight/tax, lead time, validity, availability and alternate PN/traceability proposals. It supports sequential revisions, withdrawal before evaluation, clarification and attributable correspondence without exposing competing bids.
3. Supplier PO pages expose ONLY sent POs belonging to the authenticated supplier and permitted payment-free line/status data, authorized controlled PO original downloads, acceptance/reference, delivery change and partial availability proposals, ASN with PN, quantities, serial/lot/batch, source, traceability, conformity, shelf life and exchange/loan/repair case, returns and RMA, supplier invoice notices and permitted match status, cancellation before receiving, and receipt/inspection projection.
4. Existing internal Procurement module now has a Supplier Collaboration workspace to review messages, external canonical quote links, ASN alerts and import controlled DMS originals to the canonical procurement_documents table. Technical reviewer UI supports an independently documented alternate PN decision and does not grant Quality approval. Existing Stores/Quality and Finance workflows retain decision authority.
5. New explicit member privileges separate procurement.read, procurement.respond and procurement.attach. Phase 5 document submission additionally checks rfqs and purchase_orders member grants and verifies supplier/tenant/PO/ASN lineage, restored FORCE RLS context and live QMS eligibility before each upload and after resumable completion.
6. Canonical quotation award gate rejects withdrawn, superseded, expired and technically uncleared supplier revisions. Sourcing checks supplier Quality eligibility before inviting providers. Advance shipment notices are guarded against concurrent over-advice. Historical originals remain retained and cannot be deleted by voiding Procurement metadata.

## Boundaries and Phase 10 acceptance

No automated tests, build, lint, migration, CI invocation, browser/security or real scanner/storage execution was manually performed for Phase 6. Automatic GitHub Actions may still run from commits, but Phase 6 code is not certified on that basis.

Before production: validate new Alembic upgrade/downgrade under PostgreSQL, all external role/RLS and tenant boundaries, member document grants, canonical quote/PO service imports, working technical alternate decisions and return/invoice/ASN handoffs, job delivery, concurrency/idempotence, 512 MiB scanner and shared storage, legal holds, physical Receiving/Quality release invariants, Finance no-leak boundary, mobile/browser behavior and related regression suites.

Operational release requires tenant-approved document classes, DMS retention policy, published/released specifications, malware scanner, real Finance/Procurement/Stores/QMS appointments and Phase 10 acceptance. Internal purchase/supplier approvals, alternate data approval and payment procedures have not been replaced. No Phase 7 implementation or new PR was started.

### Concurrent quotation submissions

Supplier quote submission locks the tenant-scoped canonical RFQ row before checking retry keys, the latest supplier revision and creating a new canonical Procurement quotation. This serializes both first revisions (for which no previous quote exists to lock) and replacement revisions. The original invitation, technical deviations, Quality eligibility and internal quotation evaluation gates remain authoritative. Phase 10 must exercise simultaneous same-revision requests from separate sessions and assert that only one canonical quotation and one external revision are committed; a conflict must not produce an orphan canonical quote.
