# AMO Setup Centre and Workforce Contract Flow

## Scope

This change turns the existing AMO Assets page into the tenant administrator setup centre without introducing duplicate setup tables.

The page consumes the existing canonical services and database-backed endpoints for:

- base stations and aliases through Foundations
- departments and users through Accounts Administration
- personnel identity health through Foundations
- employment-contract and work-pattern readiness through Workforce HR
- AMO logo and CRS template assets through AMO Assets

## Administrator flow

1. Create the main base and any line stations, outstations, hangars, workshops or training sites.
2. Create departments and users.
3. Open Workforce and create effective-dated contracts using a canonical primary base.
4. Assign work patterns or apply the controlled default-day baseline.
5. Upload the AMO logo and approved CRS PDF template.
6. Continue to Document Control, email delivery, billing and other enabled module settings.

The guided setup dialog and readiness checklist expose this order directly in the interface. Readiness is calculated from current records; it is not a manually ticked checklist.

## Workforce dialog correction

The contract and controlled-decision dialogs were already implemented but used a low stacking level. The setup stylesheet is imported by the global rostering stylesheet and now provides a shell-level backdrop, a dialog layer above portal navigation and drawers, a viewport-bounded editor, and sticky save/cancel actions for long contract forms.

No employment-contract schema or endpoint replacement was required. Contract creation remains the audited POST /workforce/employment-contracts workflow.

## Validation

The implementation keeps every setup action connected to a canonical service or real application route. The page is responsive from mobile screens through wide desktop displays and preserves tenant isolation by using the existing admin context and API authorization rules.
