# QMS External Provider Governance Acceptance

This acceptance note defines the release gate for the External Providers domain.

## Authority boundary

- Procurement owns commercial supplier identity and purchasing execution.
- Quality owns provider approval, approved scope, restrictions, suspension, reinstatement, governed contracts, evidence verification and Quality holds.
- A provider is not usable merely because it exists in the Procurement supplier master.

## Mandatory usage gates

The backend must reject operational use unless all applicable Quality controls pass:

1. Supplier lifecycle status is `APPROVED` or `CONDITIONALLY_APPROVED` and the supplier is active.
2. The requested purchase category is covered by a current active Quality approval scope.
3. No active Quality hold blocks the supplier.
4. Where the QMS provider profile marks a contract as mandatory, a current `ACTIVE` governed contract exists and is within its effective dates.
5. Quote award, purchase-order creation, Quality/final PO approval, PO dispatch and receiving all re-evaluate the gate rather than trusting a stale earlier decision.
6. A controlled override must carry both a reference and attributable reason and remains subject to Quality final approval.

## Provider lifecycle

The governed register covers suppliers, contractors, subcontractors, service providers, consultants, laboratories and calibration providers. Quality can place a provider under review, approve conditionally, approve, restrict, suspend, expire, reject, archive and reinstate through attributable audited transitions.

## Contract and evidence control

Provider contracts have governed lifecycle states and effective/expiry dates. Evidence is linked to the provider and, where applicable, the contract; it is independently verified and expiry-aware. Tenant row-level security applies to provider governance tables.

## Tenant timezone

QMS planner date grouping and display must resolve from tenant-owned timezone configuration, not a Nairobi/EAT constant. Invalid or absent tenant configuration falls back to UTC rather than another tenant's locality.

## Verification

Release is not accepted until the supplier-use contract tests, QMS route tests, planner timezone tests, migration upgrade and the relevant Quality/Procurement CI workflows are green on the synchronized PR head.
