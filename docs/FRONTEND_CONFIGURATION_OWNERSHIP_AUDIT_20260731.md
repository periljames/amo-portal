# Frontend Configuration Ownership Audit

Date: 2026-07-31  
Scope: AMO tenant administration, setup-time records, seeded/default catalogues, and location-aware Workforce/Rostering prerequisites.

## Release implemented in this branch

| Configuration | Canonical owner | Administrator UI | Write operations | Safety rule |
|---|---|---|---|---|
| Bases, stations, hangars, workshops and outstations | Foundations `base_stations` | AMO Setup Centre | Create, edit, activate/deactivate | Tenant-scoped canonical records; no duplicate module copies |
| Approved coordinates and geofence policy | Foundations `base_stations` | Base editor in AMO Setup Centre | Manual/aerodrome/device draft, policy edit | Explicit capture only; prompts remain disabled without coordinates |
| Independent location verification | Foundations `base_location_observations` | Base editor verification panel | Contribute, aggregate, approve, clear | Raw points are short-lived, not listed to peers, and deleted after approval |
| Aerodrome lookup | Foundations airport catalogue provider | Base editor autocomplete | Search/select only | Public dataset is advisory; operator confirms against authority/AIP data |
| Departments | Accounts `departments` | AMO Setup Centre | Create, rename/re-code, route, order, activate/deactivate, delete | Reading does not seed; deletion blocked while users or operational records reference the department |
| Users and access | Accounts `users` and role/permission records | Existing Users administration | Existing create/edit/activate workflows | Departments are selected from tenant-owned records |
| Employment contracts and primary bases | Workforce | Existing Workforce settings | Existing create/edit/effective-date workflows | Primary base references Foundations |
| Work patterns | Workforce/Rostering contracts | Existing Workforce/Rostering settings | Existing assignment/default-baseline workflows | Effective-dated and tenant scoped |
| CRS logo and template | AMO asset service | AMO Setup Centre | Upload/replace/preview/download | Controlled output assets only |

## Privacy and attendance boundary

The new location layer is a prerequisite, not a hidden attendance tracker.

1. The browser never requests location on page load.
2. A user must click a clearly labelled action before the browser permission prompt appears.
3. A draft device capture is persisted only if an authorised administrator saves the base.
4. Independent contributors submit one short-lived observation. The normal API exposes only count, contributor count, median accuracy and spread.
5. Approval writes one aggregate base coordinate and deletes the underlying observations.
6. The proximity endpoint calculates a result without storing the submitted device point.
7. Location alone cannot check a user in, check a user out, close duty or determine misconduct.
8. A future attendance command must separately verify the roster/duty state, user consent, accuracy, approved base policy and audit reason.

## Configuration candidates requiring module-owner review

The repository contains several `seed_default_*` or catalogue/default paths. Seed data is acceptable for migrations, demo tenants and explicit “install recommended template” actions. It must not silently recreate tenant configuration during a read request.

| Area | Current pattern to review | Required frontend outcome | Priority |
|---|---|---|---|
| Rostering catalogues | Default duty/constraint/catalog helpers in `apps/rostering/catalog.py`, `services.py` and governance paths | CRUD screens for duty types, shift templates, constraint profiles, skills and operating calendars, with explicit template install | P1 |
| Workforce defaults | Default work/leave structures in Workforce services | CRUD and effective-date UI for work patterns, leave types, contract templates and policy assignments | P1 |
| Finance and Inventory | Module seed script and account module bootstrap paths | Tenant chart/configuration wizard, stores/locations, units, tax/currency and approval limits | P1 when module enabled |
| Reliability | Default reliability configuration paths | Fleet/programme configuration, alert thresholds, ATA scope and report schedules | P2 |
| Quality | Compatibility/default scope helpers | Controlled setup for audit programmes, scope catalogues, finding classifications, approval routes and numbering rules | P1 |
| Notifications | Delivery defaults | Tenant-editable event preferences, escalation routes, quiet hours and mandatory-notification lock indicators | P2 |
| Training | Catalogue values and validity assumptions | Course/type/competency CRUD, validity rules and evidence requirements | P2 |
| Document Control | Existing settings coverage | Continue replacing implicit constants with controlled document types, workflows, registers and distribution rules | P1 |

## Required implementation rule for every module

Every tenant-configurable concept must have all of the following before it is considered complete:

- one canonical database owner and stable ID;
- tenant-scoped list, create, update, deactivate and safe-delete APIs;
- an administrator UI with validation, dependency counts and explicit confirmation;
- no seed-on-read behavior;
- optional defaults installed only through an explicit, audited template action;
- audit events for create/update/delete and permission checks for every write;
- import/export only after the interactive CRUD path works;
- dark/light/mobile/wide-display UX coverage;
- regression tests proving tenant isolation and preventing stale support-context data.

## Follow-up sequence

1. Convert Rostering duty/constraint catalogues into managed records and expose them in Rostering Settings.
2. Complete Workforce policy CRUD, including contract templates, work patterns and leave types.
3. Add a governed attendance event model that consumes the transient proximity endpoint only after privacy policy and employee consent are configured.
4. Add an Admin Configuration Registry showing every enabled module, its owner, CRUD readiness, unresolved seeded defaults and direct setup route.
5. Repeat the same ownership test for Quality, Training, Reliability, Inventory, Finance and Notifications.
