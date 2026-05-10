# QMS Route Map

## Status

Phase 3 and Phase 4 route consolidation has been advanced against the current uploaded codebase only.

The canonical tenant route is:

```text
/maintenance/:amoCode/qms
```

The canonical backend API prefix is:

```text
/api/maintenance/:amoCode/qms
```

Platform superusers must use:

```text
/platform/control
```

They are not tenant QMS users and must not enter `/maintenance/:amoCode/qms`.

## Implemented top-level QMS surfaces

```text
/maintenance/:amoCode/qms
/maintenance/:amoCode/qms/inbox
/maintenance/:amoCode/qms/calendar
/maintenance/:amoCode/qms/system
/maintenance/:amoCode/qms/documents
/maintenance/:amoCode/qms/audits
/maintenance/:amoCode/qms/findings
/maintenance/:amoCode/qms/cars
/maintenance/:amoCode/qms/risk
/maintenance/:amoCode/qms/change-control
/maintenance/:amoCode/qms/training-competence
/maintenance/:amoCode/qms/suppliers
/maintenance/:amoCode/qms/equipment-calibration
/maintenance/:amoCode/qms/external-interface
/maintenance/:amoCode/qms/management-review
/maintenance/:amoCode/qms/reports
/maintenance/:amoCode/qms/evidence-vault
/maintenance/:amoCode/qms/settings
```

## Backend route registry

The backend exposes:

```text
GET /api/maintenance/:amoCode/qms/route-map
```

This returns the route tree visible to the authenticated tenant user after permission checks.

## Nested route policy

Nested child routes are registered in the frontend and backend route registry. Where mature feature pages already exist, the router continues to use them. Where no mature page exists yet, the canonical QMS page loads the corresponding tenant-scoped backend endpoint and displays real returned records or a no-record state.

No static fake QMS counters are used.

## Legacy route policy

Existing legacy shortcuts must redirect to the canonical route. They must not become a second active QMS tree.

## Known limitations

Some deep workflow pages still use generic tenant-scoped QMS records. They are not yet full bespoke workflow screens. The next development pass should replace generic views one module at a time with dedicated forms, validation, workflow state machines, and evidence upload controls.
