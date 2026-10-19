# Phase 10 — Exact final verification, remediation and release decision handoff

**Do not auto-execute this phase.** Phase 9 commits occurred on original draft PR #560 \`codex/external-provider-platform-20261009\` without pytest, Playwright, Vitest, lint, typecheck, builds, Alembic execution or manual CI. Execute only when Phase 10 is explicitly authorized; do not merge until all blockers resolve. Reconcile with current \`main\` once more before approval if moved.

## Ordered execution gate and acceptance evidence

1. **Review and baseline**: capture actual final branch HEAD and main HEAD, PR #560 full commits, open reviews, Codex comments, existing GitHub Actions workflow definitions, status checks and every Phase9 matrix \`P/G\`. No source-status \`S\` is a passing test.
2. **Migration DAG**: show current heads, branches, dependencies and exact Phase9 parent; PG upgrade from empty and preexisting tenant snapshots, reversible downgrade preserving historical records; check snapshot immutable trigger, classification FK and cross-tenant RLS. Fix migrations first.
3. **Security boundary**: 2+ tenants, 2+ providers each, 2 users per same vendor, restricted grant/object, revoked grant/session, locked user, suspended provider, inactive/expired supplier, no broad DMS/Quality/Procurement authority. Attempt forced cross-tenant queries and direct-object links; require 403/404 without count leakage.
4. **Credential and account**: verify email/password with vendor key and tenant, MFA/password reset, passkey session bound origin/RP and CSRF replay/revocation, admin invite and delegated member scope.
5. **Quality source authority**: evaluate original approved scopes, regulatory certificates, independent technical/Safety/Quality checks, incoming Quality evidence, surveillance/audit independence, QMS findings/CAR/CAPA/effectiveness. Test deliberate wrong-order/stale approval.
6. **DMS/contract evidence**: same checksum from upload→object store→QMS review→controlled DMS revision. ClamAV fail closed, file ZIP bomb/MIME mismatch and revoked access, signed contract vs simple acknowledgement, legal/retention safeguards.
7. **Procurement lifecycle**: internal RFQ issue, provider quotation revisions, PO sending/ack, delivery change, shipment ASN, physical receiving and Quality hold, discrepancy, return/RMA and legitimate stock release; invoice/status trace.
8. **Maintenance end-to-end**: internal original work scope and approved site/contract, technical data publication, assigned vendor acknowledgement/progress, custody of company items, additional work approvals, independent inspections and evidence, exact certified release, return, Stores receipt, technical closure; operator/foreign/regulator permissions.
9. **Notifications**: map every requested Phase8 item to an actual authoritative source. Prove initial/noisy changes, due+overdue, source reschedule/expiry revocation, digest/quiet hours and tenant DST, current recipients, exactly-one intended in-app. Crash worker mid-send and reconcile signed Resend webhooks; show accepted/bounced/delivered/opened as distinct states.
10. **Provider 360 analytics**: compare each KPI to canonical rows including zero denominators, partial returns, reopened repair order, archived provider, evidence revision, false critical/sole-source proposal; sign off definitions with Quality/Procurement/Finance. Verify manager-only documented classification, optimistic revision and immutable snapshot with same transaction.
11. **Frontend acceptance**: all new internal and external workspaces, 403/409/422 handling, pending/empty/success/retry, responsive mobile, keyboard focus, file uploads/downloads, search/pagination and stale route change, exactly one provider record opened by deep link.
12. **Performance/HA and resource handling**: large mixed tenant count, certificate/calendar scans, import sample workbook load, file memory and streaming, actual indexes/EXPLAIN, concurrent scheduler, multi-node downloads/recovery, stalled worker, duplicate idempotency keys.
13. **Tool-driven validation** (only in Phase10): complete backend pytest; frontend Vitest, TypeScript typecheck, lint, production builds; Playwright browser+PostgreSQL; full GitHub CI and Codex review repair. Never weaken tests to pass broken functionality.
14. **Acceptance**: record observed evidence, before/after issues, clean PR review threads with actual code links, zero unresolved critical risks, separate deployment regulatory human acceptance, then approve merge according to user's instruction. No Phase10 Phase9 synthetic acceptance.

## Mandatory findings to resolve before declaring production ready

See Phase9 matrix \`P/G\` cells and risk register \`P9-01–P9-20\`: QMS audit/CAR/CAPA adapters, contract legal signature and replacement, canonical physical Stores/maintenance custody and release, provider email crash/idempotency, global record-retention controls, large export job and real source workbooks. A source implementation can exist while runtime acceptance is outstanding; a catalog name is not an implemented event.

## Actual result to report

The Phase 10 result must identify final **branch/commit**, exact GitHub status including any **new main movements**, each workflow Pass/Fail/Blocked with evidence, migration and RLS matrix, full CI names and links, remediation commit(s), performance numbers and explicit human regulatory acceptance. Until then PR #560 remains **draft and unmerged**.


## Additional mandated regression matrix from late Phase 9 remediation

1. **Untrusted register XLSX/XLSM**: malformed ZIP, encrypted member, compression bomb, >128 MiB expanded archive, >64 MiB part, excessive archive members, sheets, columns, cell length and scanned rows; confirm HTTP 413/422, memory ceiling, rollback and tenant RLS after exceptions. Also validate an actual 2,000-row legitimate workbook.
2. **Human classification**: future-dated independently VERIFIED evidence, expired evidence, revoked Quality status, evidence from another provider/tenant, concurrent revision, an archived/prospective supplier and an attempted unreferenced evidence ID. No automatic approval, suspension or reinstatement.
3. **Prospective/full controlled register**: both `is_active=true` and `false` states, CSV neutralization of formulas, 10k cap, complete tenant isolation and attributed export audit; user-visible empty/error handling.
4. **CAR control effectiveness**: valid canonical profile + `EFFECTIVENESS_REVIEW` accepted/rejected/blocked/overdue/absent and verified CAP without completed effectiveness. Compare counts with original CAR control-loop source and prove no invented assessment. Repeat findings, warranty outcomes and actual operator authority remain separate.
5. **Notification windows and transport truth**: vendor digest true/false versus global digest, source created before/after daily hour, quiet hours overlapping configured hour, differing tenant time zones and DST folds/gaps; requeue after suspension/revocation, interrupted Resend accept/commit and signed webhook bounce/delivered/open. Backend job `DELIVERED` means handoff, **not** inbox proof.
6. **Rapid provider list navigation**: type three searches, change status/page/tenant during debounce, and resolve the oldest network response last. The UI must show only the newest authorized tenant's current list, never stale supplier data.
7. **CI coverage matrix**: use the seven inspected workflow definitions recorded in `PHASE9_INVENTORIES.md` plus all matching job suites. Because GitHub path filters may miss later source areas, identify and run supplemental acceptance explicitly once Phase 10 is authorized.

Do not start these checks or merge from Phase 9. Maintain all original `P9-01–P9-20` open risk gates until actual evidence closes them.
