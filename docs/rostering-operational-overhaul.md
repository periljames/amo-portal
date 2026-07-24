# Rostering Operational Overhaul

Primary implementation issue: #347

This document is the coordination and acceptance contract for follow-on Rostering work. Production implementation is split across conflict-safe PRs. PR #349 owns the first Operating Structure and guided-setup slice; this branch must not duplicate those files.

## Ownership boundaries

- Base/station master data is owned by the shared Foundations domain.
- Personnel identity remains `accounts.users.id`.
- Permanent and temporary personnel-to-base placement uses effective-dated `user_base_assignments`.
- Roster assignments store the actual duty base for each shift.
- Training, leave/unavailability and Quality commitments remain owned by their source modules.
- Maintenance and Production remain the source of work-order/task progress used by Operations reporting.

## Administrative location

Tenant base administration is exposed under:

`System Admin -> Operating Structure -> Bases & Stations`

Rostering links to this canonical administration surface and never creates a duplicate base table.

## Base movement model

- `HOME_BASE`: permanent normal base.
- `TEMPORARY`: temporary transfer for a defined period.
- `RELIEF`: short-term operational cover.
- `TRAINING`: temporary training location.
- `OTHER`: controlled exceptional placement.

Temporary placement does not overwrite the home base. Effective-date overlap validation prevents conflicting primary assignments. The planner defaults each shift to the effective base on the shift start date in the applicable local timezone, while the roster assignment retains the actual selected duty base.

Personnel placement is distinct from base eligibility. A person may be authorised or contractually eligible to work at several bases without being actively deployed to all of them. Later implementation must not use a temporary deployment record as a substitute for licence, authorisation, contract or access eligibility.

## Additional governance requirements

- Base codes, aliases, ICAO/IATA values and names are tenant-scoped and case-normalised.
- Time zones must be validated IANA identifiers rather than unchecked free text.
- Base deactivation requires an impact check covering active/future deployments, roster assignments, work orders, training events, Quality activity and inventory locations.
- Duplicate bases require a controlled merge workflow that preserves foreign keys and adds the retired code as an alias.
- Temporary, relief and training deployments require an end date unless an explicitly authorised exception is recorded.
- Every create, update, end, cancel, deactivate, reactivate and merge action records actor, reason, before/after state and correlation ID.
- Deployment mutation uses scoped capabilities rather than broad hard-coded role checks.
- Concurrent administrative edits use optimistic concurrency; last-write-wins is not acceptable.

## UX rules

- Do not display permanent tutorial panels.
- Contextual guidance appears once per user, tenant, guidance key and version.
- Explicit acknowledgement is distinguished from closing or escaping a dialog.
- Guidance acknowledgement is persisted server-side and may use local storage only as an offline fallback.
- A small help control reopens guidance.
- Pages with missing prerequisites show an actionable modal with direct setup links and preserved return navigation.
- Hard prerequisites do not offer a misleading read-only continuation when the page has no useful read-only function.
- Editing restrictions remain visible and explain the exact missing capability.
- Optional data failures never block the main planner grid.
- Setup deep links must open the requested subsection, not merely the Setup landing tab.

## Rostering workspaces

1. Command
2. Planner
3. Operations
4. Compliance
5. My Duty
6. Setup

## Delivery order and ownership

1. PR #349: canonical Operating Structure, dated deployments and guided setup.
2. Progressive planner loading, diagnostics and full draft editing.
3. Shift library, pattern builder and controlled rule sources.
4. Actionable compliance remediation and override workflow.
5. Operations workspace with lazy work-order Gantt details.
6. Authenticated browser, permission, cross-module, slow-network and offline regression suite.

## Concurrency

- Do not modify PR #349-owned files from this documentation/test-contract branch.
- Do not modify Quality, Publications/Document Control or shared-shell files owned by other concurrent agents.
- Each implementation PR must declare its file ownership and stack on the latest merged predecessor.
- Cross-module changes should prefer new adapters, tests and service contracts over broad edits to source modules.

The complete acceptance and scenario matrix is maintained in `docs/rostering-scenario-matrix.md`.
