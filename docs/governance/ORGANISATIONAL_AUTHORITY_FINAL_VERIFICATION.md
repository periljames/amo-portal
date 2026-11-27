# Organisational authority verification — interim

Acceptance: NOT COMPLETE. Phase 1 is IN PROGRESS. Phases 2 and 3 are NOT STARTED.
Baseline: `d760894749bb9154ccf06c6fefb6046bdc3a197e`.
Branch: `feat/enterprise-organisation-authority-qms`.
Initial checkpoint: `2ce640c755a5472de24d38e2d46c231ded9fd693`.
Follow-up checkpoint: `e94ad1eeaf65c62671211e779b234585f27550f8`.
Current implementation commit: consult `git rev-parse HEAD`; the implementation
ledger identifies checkpoints without embedding a self-referential commit hash.
PR: [#575](https://github.com/periljames/amo-portal/pull/575), DRAFT, targeting `main`.

## Evidence collected

- Working tree and branch inspected; origin/main fetched and baseline confirmed.
- Metadata and patches inspected for #452, #355, #540, #570, #574, #564, #569, #557.
- Narrow import check: Accounts context router, Quality permission boundary and
  Workforce governance router imported successfully; each new route registered once.
  The first attempt was rejected by the existing SQLite runtime guard; rerun used
  explicit isolated-test settings and an in-memory URL. No operational DB was used.
- Changed Python files parsed with `ast.parse` (16 at the recorded syntax checkpoint).
- `git diff --check` completed without whitespace errors at that checkpoint.
- Reference search found no remaining `_QUALITY_ROLE_PERMISSIONS`,
  `_has_role_permission` or `assurance_permissions` consumer after consolidation.

No backend tests, frontend tests, builds, browser workflows, database migrations,
performance benchmarks or CI checks have been executed for this branch.
New test files are contracts awaiting Phase 3, not passing-test evidence.
All frontend verification must be live against the portal on this computer.

## Implemented but unverified

Accounts: persisted multi-assignment QMS access evaluator, scope/constraint denials,
position-appointment requirement for protected capabilities, batch evaluation and
self-service evaluation endpoint. QMS: dependencies and imperative checks share
that evaluator; static role fallback and import-time map mutation removed.
Workforce: current organogram/reporting resolver, explicit ambiguity/conflict
results, governed hierarchy locks, supervisor scope validation and dated manager
replacement. Existing schema is reused; no migration has yet been introduced.

## Release blockers and limitations

- Existing tenant grants must be reconciled before deployment. Users lacking
  persisted profiles now fail closed; account role labels no longer restore QMS access.
- Record-scoped QMS consumers still need to supply scope explicitly. Existing
  unscoped dependencies cannot authorize department-restricted assignments.
- Protected capability/position linkage is only one decision prerequisite. Explicit
  decision authorities, delegation, competence and reviewer assignment remain to implement.
- Domain-local administrative/role bypasses remain to audit and replace.
- Position/unit topology is current only. Dated occupancy is not historical topology;
  the organogram response explicitly declares `topology_basis: CURRENT`.
- Full reporting-writer consolidation, temporal topology and governed acting
  appointments are incomplete. Existing contract/onboarding writers still need review.
- Persistent workflow policies/instances, all QMS/DMS lifecycle integrations,
  notifications, dashboards, frontend implementation and live acceptance remain.
- PostgreSQL locking/RLS/concurrency, scale and migration acceptance are unverified.

Do not mark this programme production-ready or ready for review.
