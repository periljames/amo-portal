# Rostering Operational Overhaul

Issue: #351

## Ownership boundaries

- Base/station master data is owned by the shared Foundations domain.
- Personnel identity remains `accounts.users.id`.
- Permanent and temporary personnel-to-base placement uses effective-dated `user_base_assignments`.
- Roster assignments store the actual duty base for each shift.
- Training, leave/unavailability and Quality commitments remain owned by their source modules.

## Administrative location

Tenant base administration is exposed under:

`System Admin -> Organisation Setup -> Bases & Stations`

Rostering links to this canonical administration surface and never creates a duplicate base table.

## Base movement model

- `HOME_BASE`: permanent normal base.
- `TEMPORARY`: temporary transfer for a defined period.
- `RELIEF`: short-term operational cover.
- `TRAINING`: temporary training location.
- `OTHER`: controlled exceptional placement.

Temporary placement does not overwrite the home base. Effective-date overlap validation prevents conflicting primary assignments. The planner defaults each shift to the effective base on the shift date but permits an authorised duty-base override.

## UX rules

- Do not display permanent tutorial panels.
- Contextual guidance appears once per user, tenant, guidance key and version.
- A small help control reopens guidance.
- Pages with missing prerequisites show an actionable modal with direct setup links and preserved return navigation.
- Editing restrictions are visible and explain the exact missing capability.
- Optional data failures never block the main planner grid.

## Rostering workspaces

1. Command
2. Planner
3. Operations
4. Compliance
5. My Duty
6. Setup

## Delivery order

1. Shared prerequisite and contextual-guidance framework.
2. Canonical base/station administration and effective-dated personnel placement.
3. Planner progressive loading, diagnostics and full editing affordances.
4. Shift library and setup restructuring.
5. Actionable compliance remediation and rule classification.
6. Operations workspace with lazy work-order Gantt details.
7. Browser, permission, slow-network and offline regression coverage.

## Concurrency

This branch starts from merged PR #346 and must avoid unrelated Quality, Publications/Document Control and shared-shell work.