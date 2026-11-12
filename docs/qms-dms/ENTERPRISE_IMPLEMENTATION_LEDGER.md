# AMO Portal Enterprise QMS/DMS — Implementation and Verification Ledger

**Scope:** one consolidation PR, target `main`. **Phase 1 base:** `86a66d2d3630518a67ff3f02d5c9467cdcdfd90d`. **Initial phase:** Phase 1. **Current phase:** Phase 2, implementation in progress; no runtime acceptance.  
Update on each change with commit SHA, affected paths, test evidence and acceptance state. No unchecked coding box by itself means completion.

## Status policy

`COMPLETE`: accepted on exact current HEAD; `PARTIAL`: implemented portions but not fully verified; `DEFECTIVE`: evidenced failure; `MISSING`: confirmed missing from canonical implementation; `SUPERSEDED`: superseded by verified newer mainline owner; `NOT VERIFIED`: incomplete evidence. **Source-only additions remain PARTIAL or NOT VERIFIED until Phase 3.**

| ID | Work / operational proof | Initial status | Phase 2 canonical change candidates | Phase 3 acceptance gate |
| --- | --- | --- | --- | --- |
| DMS-01 | Preserve immutable source DOCX/PDF and SHA-256 per revision; reject unbound renditions | PARTIAL | manuals models, office_rendition/router, publication reader (#569) | checksum, version swap, forbidden mutation, large DOCX |
| DMS-02 | Faithful controlled PDF.js read, verified Word-export rendition, visible approximate fallback, retry | PARTIAL | manuals office_layout, office_rendition, reader UI (#569) | image-heavy, mixed orientation, page/heading/table Word PDF comparison |
| DMS-03 | No unverified/failed critical rendition publication | NOT VERIFIED | server publication policy and controller actions | blocked publish cases, actor/timestamp, rollback |
| DMS-04 | Secure Entra delegated auth and Graph file link/import, eTag and provenance; explicit draft only | PARTIAL (branch #569) | doc_control microsoft* modules, workspace service, reader/admin UI | OAuth/refresh/revoke, stale eTag, cross-tenant, interrupted download, Graph errors |
| DMS-05 | Accessible company library, multi-view, search/page, shared/personal views and favorites | PARTIAL | doc_control library/discovery, manual reader favorite, documentControl UI (#557) | permission/1000+ row tests, page/count consistency, keyboard and mobile |
| DMS-06 | Controlled multi-file intake, ownership and reviews | PARTIAL | existing intake/dialog/governance routes | server validation, duplicate, staged recovery, non-admin denial |
| DMS-07 | Distribution, acknowledgement, retention/evidence chain | PARTIAL | existing workspace/revision distribution and training integration | real approved revision to acknowledgment and retained proof |
| AUD-01 | Bounded authoritative checklist bindings, direct-ID confirmation | PARTIAL (branch #558) | quality template router, frontend qmsChecklistTemplates, Prepare | >100 binding committed PostgreSQL reads and tenant denial |
| AUD-02 | Frozen source lineage for every fieldwork item and evidence | PARTIAL | quality route order, execution router, fieldwork frontend | immutable version, 101st binding, source checksum and evidence linkage |
| AUD-03 | Offline idempotent replay and conflict/resume | PARTIAL | existing audit offline/commands | duplicate replay, stale mutation, cross-device, PWA recovery |
| CAR-01 | Five Whys/Fishbone/Pareto save/rework/review and multiple assigned actions | PARTIAL | current canonical RCA/loop, no new engine | real authorized browser and DB read-after-commit |
| CAR-02 | Deadline, independent effectiveness, final closure and evidence retention | PARTIAL | current loop review/effectiveness/closure guards | disallowed closure, date changes, independent verifier |
| CAR-03 | Reproduce #564 CAR real-browser CI run 41999293028 | DEFECTIVE (on #564 head) | diagnose only after Phase 2 | exact failing stage passes on final HEAD, no mocks/skips |
| QMS-01 | Risk/opportunity identification, scored assessment, controls and residual acceptance | PARTIAL | canonical Quality risk owner; SMS boundary | user lifecycle and signed acceptance/expiry/history |
| QMS-02 | Management-review agenda, quorum/attendance, inputs, decisions and action follow-up | PARTIAL | existing management-review source, avoid generic register-only UX | meeting-to-action-to-closure API + real UI |
| QMS-03 | Equipment/calibration certificate, due, quarantine, out-of-tolerance and disposition | PARTIAL | authoritative Stores/equipment + QMS oversight | overdue gate, traced impact, quarantine enforcement |
| QMS-04 | Process scope/ownership/KPIs/periodic review and control changes | PARTIAL | canonical QMS process owner | edit-authorize-review-history workflow |
| QMS-05 | Regulator/customer findings/correspondence/commitments/actions | PARTIAL | current Quality external interface, DMS correspondence | incoming to approved response and retained closure |
| QMS-06 | Reports/trends/drilldowns with defined population and denominators | PARTIAL | quality reports_router and specialist client | source-backed arithmetic, time window, export injection |
| X-01 | Manual revision → training/acknowledgement assignment and proof | NOT VERIFIED | DMS/Training APIs, no shadow tables | state transition + human acknowledgement, two tenants |
| X-02 | Supplier governance → Procurement eligibility | PARTIAL | Procurement-owned gate with Quality source references | approved/suspended purchasing acceptance |
| X-03 | Personnel authorization → permitted assignments | PARTIAL | Quality People + assignment owner | expired qualification and admin bypass negative tests |
| X-04 | Technical data and regulator obligations → impact and traceability | NOT VERIFIED | DMS, Engineering/OEM source adapters | exact version provenance, permission and amendment |
| ENT-01 | Tenant isolation, scoped roles, append-only evidence | PARTIAL | existing auth + #564 shared boundary (coordinate) | two tenants, negative writes, RLS/tested least privilege |
| ENT-02 | Storage integrity, quota, retention, production restore | PARTIAL (#564 branch) | shared platform owner, explicit dependency | object SHA, recovery drill, quota race, retention hold |
| ENT-03 | PostgreSQL migration heads, upgrade/recovery and backward compatibility | NOT VERIFIED | compose #569/#557/#564 migration branches only as required | fresh + upgrade PostgreSQL, graph, downgrade policy |
| ENT-04 | Accessibility, pagination, performance, reliable notification/error states | PARTIAL | source-preserving frontend, API and worker corrections | keyboard/screenreader/mobile, latency/limits, retries |
| ENT-05 | Final code/CI, deployment and production-readiness decision | NOT VERIFIED | final verification report | all relevant checks on exact HEAD; external blockers recorded |

## Phase checkpoints

- [x] Phase 1: fetched current main SHA and live open/merged PR metadata.
- [x] Phase 1: inspected mainline Quality, Document Control and Manuals source inventories, selected routes/models, PR diffs and migration dependencies.
- [ ] Phase 1: finish detailed line/function reconciliation of overlapping 564/569/557/558 branches and remaining legacy PRs; record findings rather than assume old branch correctness.
- [x] Phase 2 source work: incorporate coherent #569 DMS Office/Graph bridge; **NOT RUN/NOT VERIFIED**, final contract verification pending.
- [x] Phase 2 source work: reconcile #557 company-library files with main, preserve Structure and provider-evidence navigation; **NOT RUN/NOT VERIFIED**.
- [x] Phase 2 source work: port #558 authoritative paginated binding and lineage backend, Prepare and Live audit UI; **NOT RUN/NOT VERIFIED**.
- [x] Phase 2 source work: implement specialist QMS management review, risk, equipment/calibration, process and external-interface routers and UX. **PARTIAL / NOT RUN**, audit/compliance acceptance pending.
- [ ] Phase 2: finish cross-domain evidence/training/authorisations/supplier gates. Manual-revision/training linking and Inventory/calibration eligibility were added; Procurement supplier gate and existing people authorisation integration inspected, acceptance and remaining technical-data traceability remain.
- [ ] Phase 2: prepare focused regression coverage for each changed contract.
- [ ] Phase 3: reconcile latest main and all Alembic heads.
- [ ] Phase 3: reproduce CAR failure, run PostgreSQL, security, E2E, accessibility, performance, CI.
- [ ] Phase 3: record exact final HEAD, commands/results/CI and production readiness in `ENTERPRISE_FINAL_VERIFICATION.md`.

## Required update format

For each completed code item append an entry: **UTC date / requirement ID / source HEAD / changed files / canonical owner / before → after contract / migrations / affected PR overlap / test files added / tests actually executed or NOT RUN / evidence URL / remaining blocker / disposition**. Do not mark `COMPLETE` from branch narrative, a route load, mock-only test, or compiled source.

## Immediate blockers

1. Branch #569 has multiple failed GitHub checks and no published completed Phase 3 acceptance; its code is not equivalent to a verified Word layout.
2. #557 and #558 are more than 1300 commits behind main and GitHub marks them nonmergeable; must port unique code selectively.
3. #564 is external platform ownership with a failing real-browser CAR check on its current head; moving that entire branch is prohibited.
4. Live Graph Entra consent/credentials, PostgreSQL deployment and actual Word-export document fixtures were not available to this inspection. Mark those acceptance cases **BLOCKED** when reached, not passed.
5. No running project checkout and no local full application/DB runner was available in this connected GitHub-only inspection; do not claim test execution.

## Source-change log — 2026-11-11 (Phase 2, unexecuted acceptance)

| Requirement | Changes made on consolidation branch | Evidence tier | Outstanding |
| --- | --- | --- | --- |
| DMS-01/02/03/04 | Reconciled PR #569 source-linked Office rendition, manual revision models, Graph integration, client experience and migrations from HEAD `4fb9536d07588fcb7048e962f7455f15222695cf`; preserved main PDF reader; no import auto-publish claim | PARTIAL — GitHub committed source only | Microsoft consent, checksum/publish security, PDF/Word visual fidelity, concurrency, migration and failure-path tests |
| DMS-05/06 | Selective #557 library/discovery router, saved views/favorites model, multi-file upload changes, search/reader components, navigation/css. Preserved newer mainline Structure and provider evidence access; chained `docctl_261009_favorites` after `doc_m365_261028` | PARTIAL — source only | Server-side actor authorizations, query scale, accessibility, migration graph and browser proof |
| AUD-01/02 | Bounded `checklist-bindings` read with exact count, persisted direct-ID and full item lineage; frontend authoritative Prepare counts/confirmation and Live item contexts; route order preserves `checklists/parse-upload` | PARTIAL — source only | Exact >100 live tenant/DB tests, offline conflict, route map and old audit compatibility |
| QMS-02 | `management_review_workflow_router.py` uses canonical QMS tables, tenant/user/source validation, serial updates and optimistic versions, independent approval/action verification, forbidden generic writes; typed service, specialist React workflow and routed UX | PARTIAL — source only | Run PostgreSQL and browser transitions with two tenants; independent role tests, non-approver checks, retained evidence ID validation, UX accessibility and concurrent edits |
| ENT-03 | Revision ordering changed to bring library favorites after Word/365 branch; no schema execution | NOT VERIFIED | Run complete Alembic `heads/history/upgrade` on fresh and upgrade-path PostgreSQL, compare #564 and main updates |

Committed representative changes: DMS #569 tree reconciliation; QMS checklist backend/frontend commits; Document Control source remaster and responsive shell; management-review backend `31aff9557a0a92b3a82fcb8c9a7b988f87815912`, guarded generic router `3b1e2ee0e8066f34192efa797783b8bf0d8423c7`, typed service `683c13d23cf9a84e100dc7f5ba8cb33bbd20a108`, specialist page `ddcdfa81d3860fbce8558322b51dbbc7adf7e0cc` and route dispatch `40ee66b52b78d410b7cf5ed852abf48068591ee8`. Full final HEAD is mutable; refresh before verification.

**Tests executed in this phase: none.** Focused test files are committed for later execution; historical branch CI failures remain unresolved, including the explicit #564 CAR browser failure. The current draft PR is [#570](https://github.com/periljames/amo-portal/pull/570), not merge-ready and not production-ready.

## Continuation — 2026-11-11: specialist QMS hardening and cross-module source reconciliation

Repository `main` remains `86a66d2d3630518a67ff3f02d5c9467cdcdfd90d` when refreshed. Work continues solely on PR [#570](https://github.com/periljames/amo-portal/pull/570); all updates are committed source work, **not executed acceptance**.

### Changes carried forward from the latest branch HEAD

- **QMS-01 risk and opportunity governance:** `risk_governance_router.py`, `QmsRiskGovernancePage.tsx`, `qmsRisk.ts`. Staged lifecycle includes initial and residual assessments, treatment owners, evidence, verification, acceptance and SMS boundary; the original unvalidated client-selectable risk rating was a material defect. New `risk_matrix_policy.py` requires an explicit complete tenant-specific `likelihood × consequence → rating` lookup and versioned modification via `qms_settings`. `canonical_core_router.py` now prevents same-version matrix edits and requires optimistic setting comparisons; backend validates calculated ratings, blocks stale residual acceptance and snapshots the matrix with each assessment. Frontend derives rating instead of allowing arbitrary client selection. Regression contract tests added in `tests/test_enterprise_governed_risk_matrix.py` and `tests/test_enterprise_risk_matrix_policy.py`; **NOT RUN**. Remaining: approval policy for matrix change, server/schema compatibility, real tenant workflows, SMS authority and residual reporting.
- **QMS-02 management review:** governed meeting workflow added earlier; `management_review_workflow_router.py` now restricts source discovery to minimal, tenant-bounded source identity and approved identifying labels, rather than returning unrestricted full records. Retained action evidence already enforced via canonical `require_evidence_records` helper. **NOT RUN**. Remaining: independent verifier/approver permissions, source shape variants, PostgreSQL transactions and real browser.
- **QMS-03 calibration and equipment:** `equipment_calibration_governance_router.py`, `QmsEquipmentCalibrationGovernancePage.tsx`, `qmsEquipment.ts`; governed certificates, due controls, quarantine, out-of-tolerance, disposition and independent release staged. `backend/amodb/apps/inventory/services.py` now checks source QMS equipment eligibility for linked serials at issue. **NOT RUN**. Remaining: prove Inventory and equipment status agree under concurrency, serialize source checks, expiry boundary and actual quarantine/release with two tenants.
- **QMS-04 process governance:** `system_process_governance_router.py`, `QmsProcessGovernancePage.tsx`, `qmsProcessGovernance.ts`, `quality_20261111_process_performance_reviews.py`; canonical process/objective owners with independently verifiable periodic performance evidence. **NOT RUN**. Remaining: upgraded PostgreSQL FK/RLS, objective/measurement correctness and process approval workflow.
- **QMS-05 external interface:** `external_interface_governance_router.py`, `QmsExternalInterfaceGovernancePage.tsx`, `qmsExternal.ts`; staged regulatory/customer correspondence through approval, submission evidence, commitments and independent verification; retains canonical external tables. **NOT RUN**. Remaining: actual authority-side submission acceptance, deadline governance, notification semantics, immutable submission proofs.
- **QMS-06 reporting:** `reports_router.py`, `QmsReportsPage.tsx` incorporate source-backed read/report routes. **NOT RUN**. Remaining: definitions and denominator evidence, CSV injection/security and drilldown parity with source.
- **X-01 document/training:** `manual_training_impact_router.py`, `DocumentRevisionTrainingImpactPanel.tsx`, `qmsManualTrainingImpact.ts`, `dms_20261111_revision_training_links.py` link immutable published manual identity to canonical Training requirement, explicitly retaining distinct DMS revision acknowledgements. **NOT RUN**. Remaining: two-tenant Training lifecycle, rule conflicts, source checksum, inactive/expired staff.
- **X-02 procurement:** inspected existing `backend/amodb/apps/procurement/service.py` `assert_supplier_eligible`, final Quality approval and `supplier_quality_control.py`. Current canonical source checks supplier status, active holds, scope and provider-contract restrictions. **PARTIAL, existing mainline source**; do not port another supplier gate from stale QMS branches. Still prove actual purchase-order award/approval, suspension race, scope eligibility, override policy and RLS.
- **X-03 personnel:** existing `audit_assignment_guard.py`, `planner_assignment_guard_router.py`, Quality People authorization remain canonical. **PARTIAL, source presence**; end-to-end expired qualification/privilege and cross-tenant assignment rejection not independently accepted.
- **X-04 technical data:** `workspace_external_assessment_router.py`, `DocumentControlApplicabilityActions.tsx` and `workspace_applicability_router.py` own external technical-source currency and applicability. Do not create shadow QMS data. **PARTIAL, source presence**; prove exact source-revision impact through approved applicability and assigned action, including aircraft/fleet scopes, Engineering sign-off and retained evidence.
- **ENT-03 migrations:** `docctl_261009_favorites → quality_process_review_261111 → dms_training_link_261111` is the branch-intended Alembic chain after #569. **NOT VERIFIED** against deployed migration graph or #564; no upgrade/rollback acceptance performed.
- **ENT-01 evidence:** `qms_evidence_reference_validation.py` enforces real tenant-retained evidence identifiers. **PARTIAL**; multi-tenant PostgreSQL RLS and actual object retrieval pending.
- **Source cleanup:** `canonical_core_router.py` duplicate risk generic-mutation guard removed without weakening fail-closed restrictions. Management-review source lookup now selects only minimal allowed fields for the already-authorised tenant. No legacy suites were run.

### Phase 3 priority acceptance gates (not yet executed)

1. Import/startup and exact route maps for each new specialist router, including duplicate detection and generic catchall precedence.
2. Alembic `heads`, upgrade from main to consolidation on real PostgreSQL, and fresh database; enforce two-tenant RLS with negative writes.
3. Risk matrix valid/invalid/inconsistent cell configuration, version race, stale residual acceptance, evidence tampering, SMS boundary.
4. End-to-end process/equipment/external/management review transitions with actual UI, independent roles and retained immutable evidence.
5. DMS source/rendition identity, Graph failure states, Word-export fidelity and exact user permissions.
6. Known CAR real-browser run 41999293028 and #569 historical failing CI; correct defects, never weaken tests.
7. Procurement suspension/Quality hold, staff authorisations and Inventory quarantine checked at real transactional release points.
8. Current PR HEAD CI, checks and Codex comments; merge blocked until all relevant gates pass or evidenced infrastructure blockers are documented.

**Disposition:** Phase 2 source partially implemented; all new specialist flows remain `PARTIAL` and relevant external live checks `NOT VERIFIED`. PR #570 remains draft. **Production readiness: NOT VERIFIED; do not merge.**

## Phase 3 CI triage — 2026-11-11, no production acceptance

- Historical consolidation HEAD `a4cbec55a015b5103a17b2ced171a6acaa06cc51`: GitHub Actions Quality backend contract and PostgreSQL schema/RLS checks **PASSED**, but frontend CI jobs failed at source parsing. Logs: [Quality Module run 42992294970](https://github.com/periljames/amo-portal/actions/runs/42992294970), [QMS Operational UI run 42992295158](https://github.com/periljames/amo-portal/actions/runs/42992295158).
- **DEFECTIVE → source correction committed, final CI pending:** `frontend/src/services/documentMicrosoft.ts` Python docstring used in a TypeScript source; converted to TS comment. Missing JSX outer-grid closing tags in `QmsEquipmentCalibrationGovernancePage.tsx` and `QmsExternalInterfaceGovernancePage.tsx` added. These three defects blocked unrelated frontend builds; source correction does not claim passed typecheck.
- **DMS contract:** [Document Control Domain run 42992294828](https://github.com/periljames/amo-portal/actions/runs/42992294828) had 422 backend tests passed, 1 failed due to an exact old source-string enumerating only legacy views. New `shared-with-me` is an explicit tenant-restricted library view. The test now checks the original allowlisted views **plus** the new view, rather than weakening access or removing functionality. [Document Control diagnostics run 42997185240](https://github.com/periljames/amo-portal/actions/runs/42997185240) showed legacy DMS shell/presentation source-string assumptions; test requirements updated to verify new reader-safe navigation and all four library presentations (list, compact, cards, register), with original governance checks retained. Final run pending.
- **CAR historical real browser:** [run 41999293028](https://github.com/periljames/amo-portal/actions/runs/41999293028), job 127150178293 failed at the authenticated Quality response read: expected one revised response, received zero. Source tracing found `list_car_responses_for_review` suppressed latest committed response unless parent status was `PENDING_VERIFICATION`; parent may legitimately be `IN_PROGRESS` after returned/accepted CAP during rework. Handler now retrieves latest active committed response independent of parent status **after** canonical reviewer authorization, preserving read-only `mark_open` semantics. Added `test_enterprise_car_response_authority.py` negative/positive lifecycle test. **NOT YET REAL-BROWSER ACCEPTED**.
- **Cross-cutting hardening:** ported PR #512 aggregate audit archive size checks directly into `audit_archive_package_router.py`; ported PR #534 theme/adaptive filter chip fixes selectively. Evidence unchanged.
- **Risk/equipment/business hardening:** tenant risk matrix cell-validation and immutable version protection, self-attested management review attendance, source-locked Inventory calibration gate and SharePoint import serialization all committed; external Graph and real two-tenant acceptance remain pending.
- **Exact final-HEAD check:** the consolidated PR now has new CI jobs scheduled after each commit, and prior run results do NOT certify the newer HEAD. Do not merge while latest-run checks are queued, cancelled due to superseding commits or failing. Main remained at `86a66d2d3630518a67ff3f02d5c9467cdcdfd90d` when checked.

**Phase 3 result: IN PROGRESS / NOT VERIFIED. Production readiness decision: NO.** A final report will record the exact final HEAD and complete executable results after CI settles; external Microsoft tenant/credentials and Word layout visual acceptance remain blockers until tested.

## Implementation audit — 2026-11-12

All items below are **PARTIAL** pending exact-final-HEAD and live-environment acceptance. No source PR was closed/merged/retargeted.

| Contract | Source/commit | Runtime verification and remaining gate |
| --- | --- | --- |
| Selective #569/#557/#558 consolidation | Git-tree SHA/source-file comparison | All source file paths are present; 4/12/6 were adapted, 3/16 retain newer mainline ownership for #557/#558. Function-level parity and browser acceptance still required. |
| QMS/DMS route ownership | `7fcbaccf`, `11c2a6d9` | Runtime FastAPI exact endpoint and Alembic-chain assertions added to Quality CI. Quality backend contract passed on historical `e8bdad58`; final-head rerun pending. |
| Equipment/Inventory calibration boundary | `2463b9fb`, `ffa4e91e`, `91642b2e`, `f6d704af` | Unique active inventory-serial calibration owner in PostgreSQL, controlled duplicate 409. Fresh-schema migration and index assertions passed in historical Document Control Governance CI; duplicate historical rows must be reconciled before upgrading a real populated database. |
| Microsoft Graph delegated draft import | `e7eb724f`, `9011dae1`, `e8bdad58` | Canonical DOCX upload no longer commits before SharePoint eTag/source lineage; test covers one commit, replay, changed eTag. Live tenant OAuth, real download, storage consistency and cancellation still unverified. |
| Manual revision → Training | `66a1c770` | Deterministic target-person row locks serialise this DMS assignment path. A separate, cross-module Training concurrency acceptance is still required. |
| CAR effectiveness reviewer UI | `bc6c1fa5`, `cb0b3bcc`, `e5715055` | Prior exact-head run 43220214444: reviewer form selector timeout although persisted plan existed. Chromium reproduced exact label mismatch on nested select options; accessible labels and full-page trace added. Current final-head real-browser conclusion/closure acceptance pending. |
| External platform integration | PR #564 separately open | Storage quota/tenant/DR work deliberately not bulk stacked. Joint platform/QMS migration and live storage/tenant tests remain blockers; no release claim. |

### Evidence policy
On historical `e8bdad58`, 22/23 workflows passed, with CAR real browser failing. All newer commits must receive their own successful final-head CI; do not infer success from previous checks or selectively ignore failures. **DRAFT / NO GO.**
