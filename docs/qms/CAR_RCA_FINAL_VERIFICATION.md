# CAR / RCA — Phase 3 verification and release evidence

**Assessment:** 2026-10-26. **Repository:** `periljames/amo-portal`. **One consolidated PR:** [#568](https://github.com/periljames/amo-portal/pull/568). **Feature branch:** `feat/qms-car-rca-unified-20261022`. **Verified application-code snapshot before this documentation commit:** `4c7b73b1f817fb3d241bb4bade9f1cd5305df6c6`. **Merge state:** OPEN, not merged. **Evidence standard:** PASSED requires actual command/job or proven scenario, not source presence; NOT RUN and BLOCKED are not passes.

## Executive decision

**Phase 3 is not fully certified for production deployment.** All eleven PR-targeted workflows passed on application SHA `66bfdc88caba3ba71f44d72d48e9e07167a724b9`. Further strict negative contracts and actual-browser token/viewport/screenshot assertions were added after that SHA. At the time this report was first authored, the full checks for code SHA `4c7b73b1f817fb3d241bb4bade9f1cd5305df6c6` were **PENDING**. Update the run evidence below only after jobs complete.

Release blockers are not allowed to disappear on the strength of a successful mocked test: (1) production storage/backfill/restore/large-file verification; (2) direct RCA two-tenant and multi-action/concurrency acceptance; (3) private Tailnet access requiring dedicated synthetic environment credentials; and (4) upstream main reconciliation before merge. None of these blockers justifies weakening CI or granting fictitious approval.

## Continuity and upstream divergence

- Phase 1 source baseline: `docs/qms/CAR_RCA_PHASE1_BASELINE.md`, original main `75ab74c34422732f175d17cdae2acdb1879a1146`. Phase 2 ledger: `docs/qms/CAR_RCA_IMPLEMENTATION_LEDGER.md`, additive implementation and incomplete-runtime warnings.
- PR merge base: `ff86cc8d7f6469318f4ec0e5fe4523a48420542a` (as inspected). Current separately advanced main: `6b78f31e012e5021fa3bf8e6a783fa70ed5ead91`. Comparison found **3 upstream commits** not yet integrated.
- Those upstream commits add tenant QMS reference numbering, settings and report routing. Overlapping files: `backend/amodb/apps/quality/router.py`, `backend/amodb/apps/quality/service.py`, `frontend/src/pages/qms/QmsModuleWorkspacePage.tsx`, `frontend/src/services/qmsCore.ts`. **BLOCKED integration:** reconcile these four code paths against current main in a controlled branch update; rerun affected suites; do not wholesale replace their implementation or merge this PR prematurely.
- Existing authoritative CAR and audit/finding identities, current invite tokens, CAR responses, Quality governance, training gate, Assurance Case and control-loop tables remain the source of truth. No production CAR was deliberately modified.

## Migration inventory and DB evidence

- Additive migration: `backend/amodb/alembic/versions/quality_20261022_car_rca.py`, revision `quality_car_rca_261022` after `extprov_261019_oversight`.
- Tables: `quality_car_rca_rollout` (activation boundary), `quality_car_rca_documents`, `quality_car_rca_revisions`, `quality_car_rca_actions`, `quality_car_rca_mutations`, `quality_car_rca_action_events`, `quality_car_rca_pareto_snapshots`, `quality_car_response_retained_revisions`, `quality_car_invite_access_controls`.
- Eight CAR-specific evidence/control tables receive forced PostgreSQL tenant RLS. Revision/action/snapshot/retained-response tables have append-only UPDATE/DELETE prevention triggers. The downgrade refuses destruction while RCA evidence exists.
- **PASSED**: synthetic fresh PostgreSQL `alembic -c amodb/alembic.ini upgrade heads` as part of [real-browser run 40298346251](https://github.com/periljames/amo-portal/actions/runs/40298346251). **PASSED**: branch-head ancestry and control-loop PostgreSQL migration/RLS probes in [CAR Control Loop CI 40298346309](https://github.com/periljames/amo-portal/actions/runs/40298346309); Quality schema/RLS probes in [Quality Module CI 40298346302](https://github.com/periljames/amo-portal/actions/runs/40298346302).
- **NOT RUN**: downgrade on a separately seeded historical production-like database, physical restore, destructive retention approval and true backup/failover rehearsal. No old CAR or evidence was deleted as a test shortcut.

## Executed automated checks

| Check and command | Result | Verified evidence |
| --- | --- | --- |
| Quality backend `pytest -q` with the canonical Quality test list in `quality-module-ci.yml` | **PASSED — 163 tests**, 322 warnings | [run 40298346302](https://github.com/periljames/amo-portal/actions/runs/40298346302), Quality backend contract |
| Frontend `npm run test:quality` | **PASSED — 162 tests** | Same run, Quality frontend canonical contract |
| `npm run build`, stylesheet contract, TypeScript compilation | **PASSED** | Same run; CAR frontend job also PASSED |
| `pytest -q test_car_control_loop.py test_car_control_loop_governance.py test_public_invite_extensions.py test_car_rca_phase3_contract.py` | **PASSED — 55 tests** on intermediate SHA `f3baacf4264183a1250dfb4f7bcb8e066ba535f8` | [run 40354284667](https://github.com/periljames/amo-portal/actions/runs/40354284667), backend-contract |
| `python -m amodb.apps.quality.tests.postgres_car_control_loop_probe` | **PASSED** on prior tested SHA | [run 40298346309](https://github.com/periljames/amo-portal/actions/runs/40298346309) |
| CAR unit and frontend lifecycle Playwright, `qms-car-control-loop-ci.yml` | **PASSED** on prior tested SHA | [run 40298346309](https://github.com/periljames/amo-portal/actions/runs/40298346309) |
| CAR real-browser `npx playwright test tests/e2e/qms-car-control-loop-real.spec.ts --project=chromium` | **PASSED — 1 real-browser scenario** on SHA `66bfdc88` | [run 40298346251](https://github.com/periljames/amo-portal/actions/runs/40298346251); browser + real FastAPI + PostgreSQL; 59.6 s |
| Storage real write/materialize/SHA-256/delete and PostgreSQL CAR lifecycle proof | **PASSED** | [run 40298346251](https://github.com/periljames/amo-portal/actions/runs/40298346251) |
| `npm exec -- vitest run src/utils/carInviteExpiry.test.ts` | **PASSED — 4 tests** | Same real-browser run |
| QMS Operational UI CI, assurance & usability Playwright | **PASSED** on earlier snapshot | [run 40298346295](https://github.com/periljames/amo-portal/actions/runs/40298346295) |
| Quality Live Tailnet `quality-tailnet-live.spec.ts` | **BLOCKED / NOT RUN** | Requires `E2E_LIVE_QUALITY=1`, accessible test deployment, and dedicated credentials; no claim of private production connectivity |
| New invalid/revoked token, mobile viewport, screenshot checks on `4c7b73b1f817fb3d241bb4bade9f1cd5305df6c6` | **PENDING** at initial report creation | [run 40354581547](https://github.com/periljames/amo-portal/actions/runs/40354581547) |

The operational UI run reported **one existing conditional skip** in the environment-gated live planner suite. No test was skipped or assertion weakened for this PR. Build logs produced frontend warning output (warnings are not treated as proof of an error or suppressed).

## Scenario acceptance matrix A–Z

| ID | Required scenario | Status | Evidence / explicit limitation |
| --- | --- | --- | --- |
| A | Finding→authorized CAR creation | **PASSED (unit)** | Quality backend audit workflow tests cover non-NC rejection; full new-CAR UI issue not replayed here. |
| B | Invitation creation and delivery truth | **NOT RUN** | Generation used by real browser fixture; SMTP/Resend delivered/read state not independently verified. |
| C | Guest invitation without login | **PASSED** | Real PostgreSQL browser visited signed public response and submitted. |
| D | Invalid/revoked/expired/unauthorized tokens | **PASSED (unit); browser PENDING** | New unit contracts reject invalid/revoked/expired; latest real-browser negative cases awaiting CI. |
| E | Multiple assigned CAR isolation | **NOT RUN** | Sibling-token response suppressed by source; multiple simultaneous issued CARs not exercised. |
| F | Containment entry and durable draft recovery | **PASSED (entry); NOT RUN (cross-device)** | Initial browser containment saved; cross-device interrupted-save recovery not established. |
| G | Five Whys branching and evidence | **PASSED (model); NOT RUN (visual)** | Branched graph serializes, validates and rejects cycles; full browser branch editing not tested. |
| H | Fishbone create/edit/save/reload | **PASSED (model); NOT RUN (diagram browser)** | Category and parent data model round-trips; actual graphical interaction lacks dedicated real-browser coverage. |
| I | Pareto source, filtering and chart | **PASSED (validation); NOT RUN (full chart)** | Positive counts/source refs and invalid rows checked; live chart rendering/filter snapshots not exhaustively exercised. |
| J | Other RCA methods | **PASSED (schema); NOT RUN (full UI)** | Supported methods inspected: causal factor, barrier, change, human/organizational, 8D and FMEA; full method workflows not executed. |
| K | Multiple methods in investigation | **PASSED (model)** | Mixed Pareto, barrier and FMEA methods persist in serialized investigation document. |
| L | Supported causal conclusion | **PASSED (unit and browser)** | Unsupported hypotheses/unevidenced causes rejected in validation; submitted structured RCA included supported causes. |
| M | Multiple distinct corrective actions | **NOT RUN** | Browser proves one independently owned action, not multi-action decision/rework. |
| N | Owner and due date | **PASSED (one action)** | Browser submits owner/date; governed deadline changes approved in real API. |
| O | Evidence uploads/retry/failure/large files | **PASSED (small file & checksum); NOT RUN (large/retry)** | Real shared-store write/get/hash/delete and browser upload passed; 100 MB, broken network and retry not fully verified. |
| P | Concurrent drafts and server recovery | **NOT RUN** | Optimistic revision and idempotency exist in source; simultaneous browser/device race not tested. |
| Q | Submission preview and confirmation | **PASSED** | Browser opens preview and confirms/commits. |
| R | Quality reviewer rejection | **PASSED** | Real browser/API rejects RCA and CAP with recorded reasons. |
| S | Rework edit/resubmit | **PASSED** | Real browser submits modified response; API asserts latest revision; Quality page displays it. |
| T | Independent CAP acceptance | **PASSED (test fixture)** | Quality reviewer accepts RCA and CAP; not automatic on guest submission. |
| U | Implementation and evidence verification | **PASSED (one action)** | Public implementation submitted, Quality independently verifies; early closure denied. |
| V | Effectiveness plan/conclusion | **PASSED (effective scenario)** | Quality adopts plan, designated reviewer concludes EFFECTIVE with reference. |
| W | Controlled CAR/finding closeout | **PASSED (CAR); PARTIAL (finding projection)** | Governed closure sets CAR CLOSED and PostgreSQL asserts state; linked finding side effects retained in source; direct finding UI needs separate run. |
| X | Ineffectiveness/escalation/reopen | **PASSED (backend); NOT RUN (browser)** | Existing ineffective reopening unit tests passed; full negative browser treatment not executed. |
| Y | Revision history and evidence export | **PASSED (backend); NOT RUN (visual export)** | Quality backend evidence-pack and retained-response contracts passed; recipient-facing archive inspection not run. |
| Z | Cross-tenant and permission boundaries | **PASSED (unit/RLS probes); NOT RUN (RCA two-tenant browser)** | Existing tenant RLS/probes and new negative reference tests pass; full two-tenant guest/employee exploit simulation not performed. |

## Aviation QMS authority and security

- **PASSED by executed backend/browser checks:** root-cause/CAPA acceptance did not automatically close the CAR; early closure rejected unverified implementation; individual action lifecycle required Quality review; effectiveness plan had a designated independent conclusion; controlled closure remained explicit; a governed deadline change required approval.
- **PASSED by focused routes/contracts:** the old `PATCH /quality/cars/{car_id}` and canonical tenant alias cannot bypass structured closure controls; old `closed_at` stamping and unapproved governed date writes are rejected. Existing legacy CAR transition compatibility remains tested.
- **PASSED by unit/source inspection:** cause parent cycles, cross-method parent associations, unsupported causal conclusions, untraceable Pareto rows and cross-CAR attachment references are rejected. Public projection masks internal actor IDs and sibling invite list; database tables are tenant-scoped.
- **BLOCKED / NOT RUN:** real deployment tenant/provider account abuse testing with two simultaneously authenticated organizations; rate-limit load assessment; live mail server delivery/read confirmation; hostile upload fuzzing; high-volume scenarios and reverse-proxy/edge log token hygiene. Do not claim those are secure solely from source.
- **Governance source boundary:** no claim of KCAA approval or exact Part citation has been made without the authoritative controlled MOPM Issue 4 approval record and rule text. Neither regulatory acceptance nor certification privileges are created by this feature.

## Actual browser artifacts and UI limits

- Previous successful PostgreSQL CAR browser execution: [GitHub Actions run 40298346251](https://github.com/periljames/amo-portal/actions/runs/40298346251), artifact `qms-car-real-40298346251-1`, runtime storage and CAR proof logs.
- The new browser script captures actual `frontend/test-results/phase3-quality-rework.png`, `frontend/test-results/phase3-quality-closed.png`, `frontend/test-results/phase3-public-closed-mobile.png`. **Capture is NOT VERIFIED until the newest run passes and uploads the artifacts.** These paths contain synthetic test cases, not customer data.
- Previous successful browser scenario was desktop and included root-cause form, public submission, internal review, implementation and closure. It did not constitute a full accessibility audit, comprehensive Fishbone pointer/keyboard test, live Pareto visualization, tablet + mobile coverage, large-file performance test, or true offline recovery.
- Playwright trace retention is enabled on failure; a successful run does **not** imply a trace ZIP exists. Keep raw URLs/tokens out of PR descriptions, reports and screenshots.

## Cross-module regression evidence

**PASSED** in the eleven workflows on `66bfdc88`: Audit lifecycle Playwright; QMS Operational UI; Planner; Assurance OS; Live Audit Security; Document Control; Quality Module; Platform Control Plane; CAR Control Loop CI; CAR real-browser; Live Audit Setup Prepare. This supports existing audit planning, CAR register, document control, role gates, Quality and shared platform compatibility within those tests. It does **not** certify production supplier/provider sessions, email delivery, DMS failover, or Tailnet deployment.

The existing `frontend/src/services/qmsAuditHubActions.test.ts` is included in the Quality frontend test command and covers action loading, invalid backend responses, authentication expiration, timeouts and loading recovery. `test_audit_workflow_enforcement.py`, `test_assurance_operating_system_completion.py` and CAR contracts were run by Quality/CAR workflows. Historical records remain accessible by source migration design; production restore and actual archived legacy file population were not run.

## Codex review disposition

1. **P1 legacy PATCH closure bypass — RESOLVED** in GitHub thread `PRRT_kwDOQYwO-86wMD7q`. Shared `transition_car` enforces control-loop closure. Regression tests prove unauthorized old and canonical PATCH attempts are denied; legitimate governed close still works.
2. **P2 local invitation expiry shift — RESOLVED** in GitHub thread `PRRT_kwDOQYwO-86wMD7z`. `datetime-local` correctly displays local time; unchanged expiry retains its exact UTC instant including DST folds; backend UTC normalization and negative timezone checks run.
3. Both findings were verified with regression tests, and the inline GitHub threads were marked resolved. Future Codex comments and later review changes require a fresh check.

## Feature changes and exact PR file inventory

The changed-file paths below are the complete PR inventory reported by GitHub before this report itself is added. They include Phase 1/2 code and Phase 3 fixes; the Phase 3 specific additions include `test_car_rca_phase3_contract.py`, updates to `qms-car-control-loop-ci.yml`, strict real-browser cases and both review fixes.

### .github

- `.github/workflows/qms-car-control-loop-ci.yml`
- `.github/workflows/qms-car-control-loop-real-browser-ci.yml`

### backend

- `backend/amodb/alembic/versions/quality_20261022_car_rca.py`
- `backend/amodb/apps/exports/evidence_pack.py`
- `backend/amodb/apps/platform/tests/test_ops_broker.py`
- `backend/amodb/apps/quality/__init__.py`
- `backend/amodb/apps/quality/assurance_case_router.py`
- `backend/amodb/apps/quality/backfill_car_evidence.py`
- `backend/amodb/apps/quality/car_closure_guards.py`
- `backend/amodb/apps/quality/car_control_loop_guard_router.py`
- `backend/amodb/apps/quality/car_control_loop_router.py`
- `backend/amodb/apps/quality/car_rca_export.py`
- `backend/amodb/apps/quality/car_rca_export_charts.py`
- `backend/amodb/apps/quality/car_rca_models.py`
- `backend/amodb/apps/quality/car_rca_pareto_router.py`
- `backend/amodb/apps/quality/car_rca_router.py`
- `backend/amodb/apps/quality/car_rca_storage.py`
- `backend/amodb/apps/quality/public_invite_extensions.py`
- `backend/amodb/apps/quality/router.py`
- `backend/amodb/apps/quality/service.py`
- `backend/amodb/apps/quality/tests/test_car_control_loop_governance.py`
- `backend/amodb/apps/quality/tests/test_car_rca_phase3_contract.py`
- `backend/amodb/apps/quality/tests/test_evidence_pack_exports.py`
- `backend/amodb/apps/quality/transitions.py`
- `backend/conftest.py`

### docs

- `docs/qms/CAR_RCA_IMPLEMENTATION_LEDGER.md`
- `docs/qms/CAR_RCA_PHASE1_BASELINE.md`

### frontend

- `frontend/src/components/QMS/carRca/CarInviteGovernance.tsx`
- `frontend/src/components/QMS/carRca/CarRcaActions.tsx`
- `frontend/src/components/QMS/carRca/CarRcaInternalReview.tsx`
- `frontend/src/components/QMS/carRca/CarRcaParetoSource.tsx`
- `frontend/src/components/QMS/carRca/CarRcaWorkbench.tsx`
- `frontend/src/components/QMS/carRca/car-rca.css`
- `frontend/src/pages/PublicCarInvitePage.tsx`
- `frontend/src/pages/qms/QmsCarControlLoopPage.tsx`
- `frontend/src/pages/qms/QmsCarControlOperations.tsx`
- `frontend/src/pages/qms/QmsModuleWorkspacePage.tsx`
- `frontend/src/pages/qms/QmsPeoplePage.tsx`
- `frontend/src/pages/qualityAudits/CarRecordView.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditRegisterPage.tsx`
- `frontend/src/pages/qualityAudits/quality-audits-list-workspace.css`
- `frontend/src/services/qmsCarRca.ts`
- `frontend/src/services/qmsCore.ts`
- `frontend/src/styles/car-invite.css`
- `frontend/src/styles/qms/people.css`
- `frontend/src/utils/carInviteExpiry.test.ts`
- `frontend/src/utils/carInviteExpiry.ts`
- `frontend/tests/e2e/qms-assurance-operating-system.spec.ts`
- `frontend/tests/e2e/qms-audit-programme.spec.ts`
- `frontend/tests/e2e/qms-car-control-loop-real.spec.ts`
- `frontend/tests/e2e/qms-codex-review-regressions.spec.ts`
- `frontend/tests/e2e/qms-excellence-cockpit.spec.ts`
- `frontend/tests/e2e/qms-operational-semantic-regressions.spec.ts`
- `frontend/tests/e2e/qms-role-gates.spec.ts`
- `frontend/tests/e2e/qms-usability-enhancements.spec.ts`

## Release decision, rollback and next gates

**Current release verdict: NOT COMPLETE / integration BLOCKED**, even if all PR workflows later pass. The strict completion definition requires full interactive methods, concurrency/retry/large-evidence cases, cross-tenant guest/employee access testing, legacy dataset restoration and deployment integration. Those have not all been executed.

- **Deployment:** review controlled policies, apply additive migration at a maintenance boundary, validate tenant RLS before enabling real invited workflows; configure and health-check durable shared object storage. Separate stored evidence file backfill tool (`backfill_car_evidence.py`) is dry-run-first and must not be run destructively on production without verified restore.
- **Rollback:** retain database backup + object-store snapshot + application build rollback point. The migration's downgrade deliberately blocks on existing RCA evidence; do not force table drops. Prefer forward repair for populated installs.
- **Reconciliation:** bring the three upstream main commits across safely after comparing router/service/Quality UI contract differences, re-run both backend and real-browser checks, and request final review. **Do not merge this PR into main yet.**
- **Follow-up execution:** verify all checks on final application commit, inspect positive screenshot artifacts, run the missing A–Z browser/security/restore cases using synthetic identities, and update this document with actual evidence. No private Tailnet or production operations were executed in this verification.

**PR:** https://github.com/periljames/amo-portal/pull/568
