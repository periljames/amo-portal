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
- [ ] Phase 2: implement specialist QMS management/risk/equipment/process/external-interface transactions. Management review backend/UI source added, **NOT RUN/NOT VERIFIED**; other specialist workflows remain.
- [ ] Phase 2: connect cross-domain evidence/training/authorisations/supplier gates.
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
