# Aviation Procurement and Supply Chain Module

## Purpose

The Procurement department provides a tenant-scoped, controlled route from maintenance or operational demand to sourcing, purchase order, quarantine receipt, independent inspection, Quality release, inventory, and Finance matching.

Canonical tenant route: `/maintenance/{amoCode}/procurement`

The existing `/maintenance/{amoCode}/stores` route is retained as a compatibility alias and renders the same department.

## User work areas

The interface deliberately uses seven work areas:

1. **Home** — action queue, exceptions, quarantine, supplier health and integration health.
2. **Requests** — demand from Planning, Production, Maintenance, Stores or direct departmental requests.
3. **Sourcing** — RFQs, invited approved suppliers, quotations and technical/commercial evaluation.
4. **Orders** — controlled multi-stage PO approval, issue and acknowledgement.
5. **Receiving** — delivery evidence, quarantine, independent inspection and Quality release.
6. **Suppliers** — supplier identity, Finance vendor link, QMS approval scopes, restrictions and lifecycle.
7. **Control** — Quality holds, QMS finding/CAR links and Finance three-way matching.

## Safety and quality controls

- Supplier eligibility is checked against active, unexpired approval scopes.
- Active supplier, PO or receipt Quality holds block release.
- Requesters cannot approve their own requisitions.
- PO creators/requesters cannot approve their own POs.
- Receivers cannot independently inspect or Quality-release the same receipt.
- External receipts enter quarantine and do not create serviceable inventory movements.
- Only accepted receipt lines are posted to inventory after Quality release.
- The legacy purchasing approval and goods-receipt APIs are deprecated and now pass through the Procurement supplier gate.
- General inventory receipt schemas default to `QUARANTINE` rather than `SERVICEABLE`.

## Cross-module connections

| Module | Connection |
|---|---|
| Planning | Requisition source, required-by date, maintenance demand |
| Production | Requisition source and production priorities |
| Maintenance | Work order, task card, aircraft and part applicability |
| Quality | Supplier lifecycle, approval scopes, holds, findings and CARs |
| Inventory/Stores | Part master, locations, serial/lot traceability and released movements |
| Finance | Vendor master and three-way matching |
| Audit | Append-only procurement event log and shared audit events |

## API root

`/api/maintenance/{amo_code}/procurement`

The API provides dashboard/reference data, suppliers/scopes, requisitions, RFQs, quotations, purchase orders, receipts/inspection/release, Quality holds and Finance matching.

## Migration

Run:

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
```

Migration head: `procurement_20260803_full_domain`
