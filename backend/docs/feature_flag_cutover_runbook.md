# Feature-Flag Cutover Runbook (Dual-Write + Reader Cutover)

## Scope
Only approved candidates:
1. users mapper duplication
2. maintenance program (`maintenance_*` -> `amp_*`)
3. utilization (`aircraft_usage` + `technical_aircraft_utilisation` + `aircraft_utilization_daily`)
4. quality corrective actions (`qms_corrective_actions` -> `quality_cars`)

## 1) Preconditions
- Runtime verification pack executed in staging with signed artifacts.
- Production schema snapshot captured (tables, columns, indexes, constraints).
- Reconciliation dashboards live and alerting configured.
- Feature flags available and reversible at runtime.
- On-call owner + DBA owner + product owner assigned per window.

## 2) Enablement order
1. `users_mapper_cutover`
   - reader parity only first
   - then writer unification
2. `quality_car_cutover`
   - dual-write CAP->CAR
   - reader CAR-first
3. `maintenance_program_cutover`
   - template-level cutover
   - aircraft-status cutover
4. `utilization_cutover`
   - dual-write raw usage
   - reader cutover
   - derived-table source lock to canonical raw

## 3) Parity thresholds (must hold before next stage)
- **Users:**
  - row count delta: 0
  - auth error rate increase: <= 0.1% absolute
  - duplicate `(amo_id,email)` introduced: 0
- **Quality CAP/CAR:**
  - `finding_id` coverage in CAR: >= 99.99%
  - status parity: >= 99.9%
  - assignee parity: >= 99.9%
- **Maintenance:**
  - due/overdue count variance per aircraft: <= 0.5%
  - `next_due_*` sampled checksum parity: >= 99.9%
- **Utilization:**
  - per-day per-aircraft hours/cycles drift: 0 (or approved exception)
  - derived daily parity from canonical raw: >= 99.9%

## 4) Rollback triggers
- Parity threshold breach for 2 consecutive intervals.
- Error budget burn > 20% in 1 hour attributable to cutover flags.
- Authentication failures or permission anomalies after users cutover.
- Data drift growth trend (not converging) during dual-write period.
- On-call declares unsafe state.

## 5) Rollback steps (operator sequence)
1. Toggle candidate reader flag back to legacy path.
2. Keep dual-write enabled temporarily to avoid fresh divergence.
3. Capture incident snapshot (metrics + reconciliation deltas).
4. If needed, disable dual-write and freeze writes in affected endpoints.
5. Rebuild parity baseline and open remediation ticket.
6. Resume only after new sign-off.

## 6) Required monitoring during dual-write and reader cutover
- Write success/failure rate by table and endpoint.
- Dual-write mismatch counters by candidate key.
- Read path distribution by feature flag state.
- Latency p95/p99 and DB lock wait metrics.
- Drift dashboards:
  - users key parity (`amo_id/email`, `staff_code` mapping)
  - maintenance due/overdue parity
  - utilization daily sums parity
  - CAP/CAR finding coverage and status parity
- Alert routing: on-call app + DBA + product owner.

## 7) Exit criteria for each candidate
- Dual-write drift is zero (or waived exceptions) for full observation window.
- Reader cutover stable for agreed period without trigger events.
- Rollback tested in staging and documented.
- Stakeholder sign-off recorded.
