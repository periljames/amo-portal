# Phase 7 — Contracted Maintenance and Technical Work Management

**Single development branch / PR #560:** `codex/external-provider-platform-20261009`. Technical source is implemented for review. It is **not** certified as accepted, migrated, tested, typechecked, production-ready or regulator-approved. Phase 8 has not started.

## Regulatory basis and boundaries

Controls are derived from Safarilink **Draft MOPM Issue 4 §2.23**, especially §§2.23.3–2.23.6, with cross-references to §§2.20 (external component repair/dispatch), 2.13–2.14 (maintenance records), 2.2 (receipt and inspection), 2.9 (repairs), 2.16 (maintenance releases), 3.13 (contractor audit) and Part 4 (operator/foreign aircraft). The draft is not yet a final Authority-approved manual. Check the final controlled MOPM before release.

1. **Technical owner:** Base, Line or Workshop Maintenance Manager initiates, reviews, authorizes, dispatches and technically accepts the relevant function. A commercial purchase order or supplier acknowledgement **never** constitutes technical maintenance authorization.
2. **QMS:** Independent Quality Manager qualification check must precede authorization. Supplier status, active Quality holds and restrictions, exact approved class/rating/site capability, signed effective governed agreement, original DMS revision and separately QMS-verified evidence are checked live at work transitions. QMS reviews do not create CRS or permit a supplier to exercise Safarilink certification privileges.
3. **Safety and foreign requirements:** Work orders collect operator, State-of-Registry and foreign authority/approval references, release wording, safety assessment and competent authority references. They fail closed when declared mandatory conditions are missing. Source references do not independently prove a foreign approval; the responsible Maintenance Manager and Quality must verify the records.
4. **Controlled work instructions:** Exactly identified asset, defect, location, function, work package/repair-order reference, maintenance data revision, inspection/test criteria, release requirement and coordinator. Where a current published technical original is linked, vendor download additionally needs explicit DMS document scope, tenant/provider grant and exact revision. A generic unrestricted DMS download is never exposed.
5. **Distinct commercial boundary:** Optional issued PO is checked against the same tenant/supplier before dispatch. Provider requests for variation record both technical data and commercial reference; written amended work authorization and technical decision are mandatory and commercial approval cannot replace them.
6. **Provider assignment:** An active external identity grant must explicitly contain this work order ID in `object_scope_json.contracted_work`. Only that named provider can see the order. A responsible Manager may assign an already active, eligible provider member to a specific order.
7. **Controlled lifecycle:** Draft → technical scope review → Quality agreement check → awaiting authorization → authorized → dispatch → provider acceptance → work in progress → completed → release submitted → returned → Stores inspection → technical acceptance → closure. Additional work is a distinct blocked state until Maintenance Manager decision. Holds, cancellations, rejection, rework and reopening require attributable actions.
8. **Company property:** Internal Stores registers items/serial/quantity/stores references and controls dispatch, reconciliation and disposition. Provider may acknowledge receipt only after Stores dispatch. No portal custody transition independently changes canonical stock, quarantine, inspection or serviceability.
9. **Controlled originals:** Providers upload work-scoped originals using existing Phase 5 small-file and resumable/scanned/hash-verified DMS intake. Separate DCO retention, Quality review and staff work-evidence linking are required before evidence satisfies technical closure. Originals and their SHA-256 provenance remain in the DMS retention domain.
10. **Certification/technical closure:** A contractor certifies only under its **own** approval, with separately authorized staff. The portal records release evidence, but does not issue CRS or maintenance release. Technical acceptance/closure blocks on unresolved additional work, un-reconciled property, mandatory release and maintenance records, tests, independent inspection, Safety evidence and outstanding discrepancies. Commercial completion does not delete regulatory history.

## Source map

- Migration: `backend/amodb/alembic/versions/external_providers_20261016_contracted_work.py` — tenant-isolated work orders, immutable technical event log, additional-work requests, custody, linked governed evidence, RLS and restricted relations.
- Backend: `backend/amodb/apps/procurement/external_contracted_work_router.py` — internal and partner work APIs, guarded transitions, site/agreement/Quality gates and assignment.
- Existing evidence integration: `external_provider_documents_router.py`, `external_partner_router.py`, published DMS document/retention and Quality verification.
- Internal frontend: `frontend/src/pages/maintenance/ContractedWorkModule.tsx`; provider frontend: `frontend/src/features/externalPartner/PartnerContractedWork.tsx`. Both use existing auth, module boundaries and standard API request contracts.
- API roots: `/api/maintenance/{amo_code}/contracted-work` (employee roles) and `/api/external-provider/partner/{tenant_slug}/maintenance-work` (provider grant).

## Not replaced or implied

No competing Procurement, DMS, Safety, Stores, Quality, technical-records or maintenance certification engines were created. Work-order custody events are subordinate coordination records, not canonical stock transactions. Completion evidence and a provider-issued maintenance release do **not** automatically return an aircraft or item to service. Work package references need canonical validation or a specific controlled MOPM §2.20 repair order.

## Deferred Phase 10 acceptance

Do not claim completion or production readiness until the actual Alembic head upgrades/downgrades, tenant/provider RLS isolation, multi-session membership revocation, role matrix, QMS holds, scope expiry during execution, foreign acceptance conditions, agreements/DMS hashes, workflow guard paths, approval/rework, unauthorized supplier document access, large uploads, Stores and maintenance-data integrations, real browser UX, notifications, 2,000-page DMS regression and all existing CI are verified without weakening assertions. Requirements needing operational authoritative integration must stay gated/blocked rather than invented.

Do not start Phase 8 or merge PR #560 until the user directs it.
