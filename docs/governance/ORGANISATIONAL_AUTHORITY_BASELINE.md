# Organisational authority baseline

Inspected 27 November 2026. Repository: `periljames/amo-portal`.
Initial clean checkout: `main`; fetched `origin/main` and confirmed both resolve to
`d760894749bb9154ccf06c6fefb6046bdc3a197e`.
Development branch: `feat/enterprise-organisation-authority-qms`.
No matching dedicated organisation/authority PR was found in the open-PR search.
One draft programme PR will target `main`; never auto-merge it.
No AGENTS.md was returned by repository/parent searches.

## Canonical owners confirmed

- `accounts/models.py`, `accounts/access_control.py`: identity, persisted profiles,
  capabilities, capability bindings and effective role assignments. Assignment
  department scope already exists. Primary profile remains presentation metadata.
- `workforce/governance_models.py`: units, positions and dated personnel placements.
  No second corporate organisation model is introduced.
- `workforce/supervisor_governance.py`: supervisor eligibility and reporting resolution.
- `workforce/governance_directory.py`, `governance_mutations.py`: catalogue and personnel writes.
- `quality/tenant_security.py`: shared read/write dependencies and imperative checks;
  restores PostgreSQL transaction-local RLS context after transaction boundaries.
- `workflow/engine.py`, `registry.py`, `guards.py`: shared domain transition and audit
  infrastructure, consumed by Quality, Training and Reliability. No approval policy,
  durable workflow instance or reviewer assignment is implemented there yet.
- `tasks/models.py`: durable user tasks already exist; reuse rather than duplicate.
- `notifications/models.py`: queued email/delivery records already exist. Transactional
  outbox integration still requires deeper inspection before workflow implementation.

Paths above are relative to `backend/amodb/apps/`.

## Initial findings

1. Both QMS permission entry points returned early for tenant administrators.
2. QMS had a static wildcard map, SQL capability lookup, primary-only assignment
   evaluation, and fallback when capability tables/definitions were absent.
3. `quality/assurance_permissions.py` mutated that map during package initialization.
4. Workforce positions already reference access profiles and reporting positions.
5. `governance_directory.upsert_position` referenced `access_control` without importing it.
6. Supervisor mutation overwrote the appointment's historical supervisor in place.
7. Replacement placement creation could flush the previous placement's shortened
   end date before restoring the replacement's original end, violating date checks.

These are source findings, not runtime verification results.

## Existing PR reconciliation

Metadata and actual per-file patches were fetched for all eight named PRs.
Exact refs and file inventories are in `ORGANISATIONAL_AUTHORITY_PR_BASELINE.json`.
All eight were open when inspected. No source branch was merged, copied or closed.

| PR | Observed scope and treatment |
| --- | --- |
| #452 | Adds a separate Accounts corporate/reporting model absent from this main. Conflicts with the required canonical Workforce owner; do not import those models/routes. Directory pagination already has a current Workforce owner. Further unique UX reconciliation belongs to Phase 2. |
| #355 | Targets `agent/rostering-operating-structure-help`, not main. Scoped operating-base/deployment governance is independently owned. Preserve current Foundations/Workforce; no wholesale cherry-pick. |
| #540 | Frontend People visual corrections, independently open. Preserve newer People lifecycle; reconcile relevant styling against the current UI in Phase 2. |
| #570 | QMS/DMS consolidation with broad lifecycle/storage overlap. Independently owned; domain integration must adapt current owners, not replace routers from this branch. |
| #574 | Public CAR capability/invitation boundary. Independently owned; do not impose employee organisational access on public invitation routes. |
| #564 | Platform, tenant/session, billing/storage security. Independently owned; retain platform isolation and subscription boundaries. |
| #569 | Office rendition/Microsoft working-document integration. Independently owned; no extra DMS lifecycle introduced here. |
| #557 | Company document library, independently owned; no duplicate document library introduced here. |

File-level incorporation decisions for later phases remain incomplete. PR metadata
and historical CI claims are not acceptance evidence for this development branch.
