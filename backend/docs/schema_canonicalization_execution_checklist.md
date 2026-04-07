# Schema Canonicalization Execution Checklist (Implementation-Ready)

## Order of execution (by risk and dependency)

### Phase 0 — Preconditions / guardrails (highest dependency)
- [ ] Freeze new schema overlap introductions (PR policy + lint/check for duplicate `__tablename__`).
- [ ] Enable per-table row-count telemetry by AMO for all candidate tables.
- [ ] Add reconciliation log table(s) for unresolved key mappings (no destructive actions).
- [ ] Add feature flags: `users_mapper_cutover`, `maintenance_program_cutover`, `utilization_cutover`, `quality_car_cutover`.
- [ ] Define parity SLOs and rollback thresholds for each candidate.

### Phase 1 — Users mapper duplication (low DB risk, high auth criticality)
- [ ] Replace direct imports of `amodb.models.User` with accounts-layer user service contract.
- [ ] Implement compatibility aliases for legacy fields (`user_code`, `amo_code`, `department_code`).
- [ ] Run parity checks: auth success rate, unique email/staff constraints, row-level field parity.
- [ ] Keep rollback switch active until 2 stable releases.

### Phase 2 — Quality CAP -> CAR (bounded scope, moderate workflow risk)
- [ ] Add/confirm any missing CAR columns needed for CAP compatibility.
- [ ] Backfill CAP rows to CAR by `finding_id` one-to-one reconciliation.
- [ ] Enable dual-write from CAP endpoints to CAR.
- [ ] Switch readers to CAR-first query paths.
- [ ] Keep CAP fallback reads behind flag until parity target is sustained.

### Phase 3 — Maintenance program legacy -> AMP tables (high relational risk)
- [ ] Expand AMP schema for category/legacy semantics if required.
- [ ] Backfill `maintenance_program_items` -> `amp_program_items` with deterministic key map.
- [ ] Backfill `maintenance_statuses` -> `aircraft_program_items` via mapped program ids.
- [ ] Run per-aircraft due/overdue parity checks and sampled value checksums.
- [ ] Switch fleet and CRS readers, then writers.

### Phase 4 — Utilization canonicalization (highest data-volume/drift risk)
- [ ] Confirm canonical raw ledger (`aircraft_usage`) and required metadata columns.
- [ ] Backfill `technical_aircraft_utilisation` into canonical raw ledger with idempotent key.
- [ ] Run dual-write for 60 days from technical-records writer paths.
- [ ] Materialize/refresh `aircraft_utilization_daily` strictly from canonical raw table.
- [ ] Cut readers after sustained zero-drift windows.

### Phase 5 — Legacy retirement (only after retention + audit sign-off)
- [ ] Rename legacy tables/paths to `*_legacy` (non-destructive, reversible).
- [ ] Maintain read-only retention window with monitoring.
- [ ] Execute drop migrations only after retention, sign-off, and backup validation.

## Explicit blockers and unknowns
- **Live DB drift unknown:** ORM/migration intent may differ from runtime schema; must inspect production catalogs before cutover.
- **ID/domain mapping unknowns:** `amo_code -> amo_id` and `department_code -> department_id` may contain unresolved historical codes.
- **Enum mapping risk:** `qms_corrective_actions.status` to `quality_cars.status` may require non-trivial mapping table.
- **Tail/serial normalization risk:** `tail_id` and `aircraft_serial_number` may not be one-to-one across all tenants.
- **Hidden writers risk:** scripts/jobs/integrations may write legacy tables outside routers/services.
- **Retention policy dependency:** legal/compliance retention windows for audit/history tables must be approved before drops.

## Non-goals in this phase
- No destructive migration SQL.
- No table drops or merges executed yet.
- No runtime data mutation outside planned backfill design.
