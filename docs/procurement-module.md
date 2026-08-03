# Aviation Procurement and Supply Chain Module

## Scope

Procurement is a first-class tenant department with the canonical route:

`/maintenance/{amoCode}/procurement`

Stores remains a separate inventory and custody department at `/maintenance/{amoCode}/stores`. It is not a Procurement alias.

## Work areas

1. **Command** — action queue, high-contrast exceptions, quarantine, supplier health and integration status.
2. **Requests** — requisitions from Planning, Production, Maintenance, Stores and departmental demand.
3. **Sourcing** — RFQs, approved supplier invitations, quotations and evaluation.
4. **Orders** — purchase-order preparation, staged approval, issue and acknowledgement.
5. **Receiving** — delivery evidence, quarantine, independent inspection and Quality release.
6. **Suppliers** — supplier identity, Finance vendor linkage, approval scopes, restrictions and lifecycle.
7. **Quality Control** — Quality holds, receiving disposition, findings, CAR links and Finance three-way matching.
8. **Documents** — immutable linkage of scans, physical originals, DMS revisions and external-system records to the exact Procurement record, with Quality verification where applicable.

## Department ownership

| Department | Ownership |
|---|---|
| Procurement | Requisitions, sourcing, quotations, purchase orders, expediting and supplier coordination |
| Stores | Physical custody, stock locations, serial/lot control and inventory movements |
| Quality | Supplier approval, restrictions, inspection policy, holds and release authority |
| Finance | Vendor payment profile, budget control, invoice matching and settlement |
| Planning and Production | Demand, required dates and operational priorities |
| Maintenance | Work-order, task-card, aircraft and part applicability |

## Controls

- Supplier eligibility requires an active, unexpired approval scope covering the purchased category.
- Active supplier, purchase-order or receipt Quality holds block controlled actions.
- Requisitions follow `DRAFT → SUBMITTED → technical approval → budget approval → SOURCING → APPROVED`; there is no direct sourcing bypass or advertised bypass action.
- Requesters cannot approve their own requisitions.
- Purchase-order creators and requesters cannot approve their own orders.
- Receivers cannot independently inspect or release the same receipt.
- Incoming material enters quarantine.
- Serviceable inventory movements are created only after inspection acceptance and Quality release.
- Invoice matching uses approved purchase-order value and Quality-released receipt value.
- Procurement actions, including evidence links, Quality decisions and voids, are recorded in both Procurement and shared audit event ledgers.
- Quality evidence decisions lock the selected database row so only one concurrent verification or rejection can become final.
- File creation, database serialization and commit share one controlled transaction boundary: failed creation or commit removes the untracked file, while no post-commit failure can delete committed evidence.
- Active-only evidence pagination removes a newly voided row before calculating the next offset, preventing skipped retained records.
- Retained evidence defaults to the persistent mounted root `/srv/amo/uploads/procurement-documents` and can be overridden with `PROCUREMENT_DOCUMENT_DIR`.

## API

Root: `/api/maintenance/{amo_code}/procurement`

- Dashboard and reference data
- Suppliers and approval scopes
- Requisitions
- RFQs and quotations
- Purchase orders and staged approvals
- Receipts, inspection and Quality release
- Quality holds
- Finance three-way matching
- Retained Procurement evidence list, optional file upload, physical-record registration, DMS/external-system links, download, atomic Quality verification and immutable void

## Deployment

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
```

Migrations: `procurement_20260803_full_domain`, `procure_20260803_docs`

Set the persistent evidence root in the deployment environment:

```bash
PROCUREMENT_DOCUMENT_DIR=/srv/amo/uploads/procurement-documents
```

## Validation

The focused Procurement validation executes all three source-contract suites, Python compilation for Procurement and Inventory, and the strict production frontend typecheck/build. Repository-wide release, Document Control, Publications, migration, browser-acceptance, and performance gates remain the final merge checks.

## Acceptance checklist

- [x] Procurement is a first-class department.
- [x] Procurement has a dedicated Command page with partial-failure loading and action alerts.
- [x] Navigation is limited to eight focused work areas.
- [x] Stores is separate and is not a route alias.
- [x] Supplier approval and scope controls are enforced server-side.
- [x] Requisition, RFQ, quotation and purchase-order workflows are implemented.
- [x] Requisition technical and budget approvals cannot be bypassed before sourcing.
- [x] The removed sourcing-bypass action is absent from the service, request schema and router authorization contract.
- [x] Multi-stage approval and segregation of duties are enforced server-side.
- [x] Receipt, quarantine, inspection and Quality release are implemented.
- [x] Finance vendor and invoice-matching links are implemented.
- [x] Planning, Production, Maintenance, Quality, Stores and Finance links are represented.
- [x] Legacy purchasing endpoints, fields and service helpers are removed.
- [x] Tenant isolation and append-only event evidence are implemented.
- [x] Signed physical forms and external-system exports can be uploaded and linked to exact records.
- [x] File size, extension, MIME, signature, duplicate hash and safe-path checks are enforced.
- [x] Failed pre-commit evidence creation removes any untracked retained file.
- [x] Successful commits cannot be followed by cleanup that deletes the committed retained file.
- [x] Quality evidence enters a pending state and can only be verified, rejected or voided by independent Quality authority.
- [x] Concurrent Quality evidence decisions are serialized so the first committed decision remains final.
- [x] Evidence link, verification, rejection and void actions are written to both Procurement and shared audit ledgers.
- [x] DMS document and revision IDs, physical storage references and external-system links are supported without forcing a duplicate upload.
- [x] Evidence records use a persistent mounted storage root.
- [x] Active-only evidence pagination remains aligned after a record is voided.
- [x] Upload progress, drag-and-drop, file-type guidance, empty states and recovery actions are exposed in the UI.
- [x] Success, warning and failure feedback uses distinct visual and audio cues.
- [x] Loading, refresh, upload and modal transitions respect reduced-motion preferences.
- [x] Source-contract regression tests cover routing, quarantine, supplier gates, lifecycle, evidence retention, transaction cleanup, pagination, atomic decisions, dual-ledger audit and cross-module links.
