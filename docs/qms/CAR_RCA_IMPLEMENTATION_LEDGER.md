# QMS CAR / RCA — Implementation and Consolidation Ledger

**Repository:** periljames/amo-portal  
**Feature branch:** feat/qms-car-rca-unified-20261022  
**Baseline main SHA:** 75ab74c34422732f175d17cdae2acdb1879a1146  
**Phase 1 baseline document commit:** cbcd4aceafaf6170b59208a51332880dcf767633  
**Review date:** 2026-10-22  
**Rule:** One feature branch and one consolidated draft PR for Phases 1–3. No merging into main. Do not change application code in Phase 1, or manually run pytest/Playwright/Vitest/lint/typecheck/builds/CI in Phase 1 or 2.

## State definition
- **EXISTS:** specific implementation found in the inspected source, not runtime certification.
- **PARTIAL:** building blocks exist; end-to-end path/requirements not established.
- **MISSING:** required function not found in identified owning source.
- **DEFECTIVE:** current implementation does not satisfy a known functional requirement.
- **NOT VERIFIED:** no sufficient source or runtime evidence to reach a conclusion.

## Baseline and Phase Summary

| Phase | Work | State | Exit gate |
| --- | --- | --- | --- |
| 1 | Map live code, historical work, exact routes, defects and safe architecture | PARTIAL — source mapping documented; runtime NOT VERIFIED | Both Phase 1 docs committed in same branch; stop here |
| 2 | Implement shared structured CAR RCA, drafts, corrective actions, security and UX | MISSING | Source fixes delivered on same PR, with migration/backward compatibility and traceable ledger updates |
| 3 | Test, repair, browser acceptance, PR review and cleanup | NOT VERIFIED | All relevant suites and CI green, skips understood, no waived checks, no premature merge |

### Non-regression rules

The authoritative CAR record remains **quality_cars** with existing Quality Review state machine (backend/amodb/apps/quality/router.py), **quality_car_responses**, **quality_car_actions**, and **quality_car_attachments**. The governed evidence-oriented RCA owner is **quality_investigation_entries / quality_assurance_cases**, and actual closure is controlled by **quality_car_control_profiles / quality_car_milestones**. Never replace these with a second CAR engine; use tenant-safe associations/projections. Maintain the existing PublicCarInvitePage, canonical public CAR adapter, current QualityCarsPage and QmsCarControlLoopPage. Preserve old IDs/statuses/invites/responses/evidence and audit-finding links; current CAR acceptance must not imply implementation, effectiveness or closure. Do not silently expand guest tokens into tenant-wide read access. Never delete or relax a test to obtain a passing status.

## Requirement-by-requirement implementation register

| ID | Source-confirmed finding | State | Concrete Phase 2 work | Phase 3 verification |
| --- | --- | --- | --- | --- |
| F01 | PublicCarInvitePage.tsx:645-659 validates root-cause as nonempty narrative; router.py:6913-6920 likewise allows textual explanation without structured causal chain | DEFECTIVE | Introduce structured RCA readiness enforced server-side for new-governed responses, retaining legacy submissions and compatibility; require evidence-linked supported conclusion | New responses cannot bypass structure; historical CAR remains readable |
| F02 | AnalysisInvestigation.tsx:56-71 offers Five Whys and Fishbone methods, category and parent selection, not an interactive Fishbone diagram/guided branching | PARTIAL | Build shared guided 5-Whys branching editor and editable accessible Fishbone with text fallback; persist entries with stable IDs, parents, factual status and evidence | Diagram works on desktop/mobile/keyboard; refresh retains all branches and authors |
| F03 | AnalysisQuantitative.tsx shows Pareto from authorized QMS analysis, but not a CAR-scope reproducible guest investigation | PARTIAL | Add provenance-aware bounded CAR-specific Pareto source/sample/period and saved snapshot; avoid revealing unrelated tenant findings to bearer-token guests | Counts and cumulative percentages validated, zero/small samples handled, persisted/independently reviewable |
| F04 | qmsCarInviteDraft.ts:19-45 persists only in sessionStorage by car_id, discards drafts when server revision changes | DEFECTIVE | Implement durable server drafts with tenant/token scoping, optimistic revision, idempotent debounced save, conflict recovery and safe import of existing session drafts | Two devices/tabs; stale revision 409; intermittent network and reload; no lost edits |
| F05 | router.py:6768-6800 returns up to 25 related CARs with their bearer invite_token; PublicCarInvitePage.tsx:700-707 automatically loads tokens; invite_token model has no explicit expiry/revoke columns | PARTIAL | Verify exactly scoped grants; remove unauthorized transitive token expansion; add expiry/revocation/rate limiting/no-store policies without breaking issued invitations; test public RLS | Wrong tenant, sibling CAR, revoked/expired token, replay, internal API denied |
| F06 | Existing control milestones track CAR stages, whereas corrective_action remains summary text, not individual owned and verified actions | PARTIAL | Inspect reusable tasks model first; add tenant-qualified per-action owners/deadlines/evidence/implementation/review only where missing | Multiple actions independently reviewed; missing action prevents false completion |
| F07 | assurance_case_router.py:332-400 stores governed effectiveness plan/conclusion; car_control_loop.py:316-372 supplies separate close gates | PARTIAL | Associate CAR RCA/corrective action with independent effectiveness plan, observation window, evidence, outcome/rework, retaining current authority | Accepted plan never closes CAR automatically; independent assessment and ineffective outcome blocks closure |
| F08 | router.py:116-118 and 7322-7389 use local generated file paths and metadata; actual shared storage/HA not established | PARTIAL | Trace DMS/object storage, validate uploads, checksum/storage consistency, atomic rollback, quotas, retries and download permissions | Missing/bad/large files, upload loss/duplication and restore; evidence checksums preserved |
| F09 | public_invite_extensions.py:273-279 replaces original public GET/PATCH; car_operational_route_order.py:35-96 clones canonical tenant routes | PARTIAL | Respect current guarded route owners and static-first promotion; no duplicate paths/catch-all shadowing | FastAPI route inventory, old + canonical contract and method-resolution tests |
| F10 | Public, internal Quality CAR, Assurance Case and control-loop screens are separate projections and styles | PARTIAL | Integrate concise step navigation, error/empty/loading/conflict states and shared next-action guidance; no duplicate CAR page | Real-browser accessibility/focus/responsive/performance across complex CARs |
| F11 | router.py:6922-6928 deletes recalled unreviewed response row before resubmission | PARTIAL | Retain immutable response/event revisions without duplicate active Quality-review queue | Recalled/resubmitted historical evidence attributable; exactly one active reviewable response |
| F12 | Deployed token security, provider grants, true independence, email delivery truth and runtime tenant isolation not probed | NOT VERIFIED | Trace IAM/RLS/proxy/notification/provider linkage source; implement only verified fixes | Multi-tenant PostgreSQL, real guest/provider browser, Quality reviewer independence, operational/CI checks |

## Exact source locations to inspect/modify during Phase 2

**Public and CAR lifecycle:** backend/amodb/apps/quality/router.py; public_invite_extensions.py; schemas.py; models.py; service.py; car_response_workflow.py; tenant_security.py.  
**Control and effectiveness:** car_control_loop.py; car_control_loop_router.py; car_control_loop_guard_router.py; car_control_loop_authority_guard.py; car_control_loop_evidence_guard.py; car_control_loop_models.py; effectiveness_response_router.py.  
**Structured investigation:** assurance_case_router.py; assurance_case_models.py; assurance_evidence_register.py; related verification/authorization services.  
**Composition and precedence:** backend/amodb/apps/quality/__init__.py; car_operational_route_order.py; car_control_loop_route_order.py; assurance_case_route_order.py; canonical_router.py.  
**Historical migrations:** backend/amodb/alembic/versions/quality_260808_assurance_cases.py and quality_260811_car_loop.py; verify current HEADS before naming any new revision.  
**Frontend:** frontend/src/pages/PublicCarInvitePage.tsx; CanonicalPublicCarAccessPage.tsx; QualityCarsPage.tsx; qualityAudits/CarRecordView.tsx; qms/QmsCanonicalPage.tsx; qms/QmsAssurancePage.tsx; qms/QmsCarControlLoopPage.tsx; qms/QmsCarControlOperations.tsx; qms/analysis/AnalysisInvestigation.tsx; qms/analysis/AnalysisQuantitative.tsx; portalRoutes.tsx; App.tsx.  
**Services:** frontend/src/services/qmsCore.ts; qmsCarInviteDraft.ts; qmsCarControlLoop.ts; qmsCarControlEvidence.ts; qmsAssuranceCases.ts; qmsAnalysis.ts; qmsRegisters.ts; qmsAuditExternalAccess.ts; apiClient.ts.  
**Styling:** frontend/src/styles/car-invite.css; car-invite-responsive.css; existing QualityEnhancementsHost / QualityEnhancementsRouteGate, reuse existing classes.

The specific need for any new schema/table/route/file is **NOT VERIFIED** until a Phase 2 code-owner and migration inventory. Proposed optional new focused components under frontend/src/components/QMS/carRca/ are *not* asserted to exist. Avoid new unrelated platform components.

## Prior work incorporation and merge safety

| Previous PR | Verified state | Integration decision |
| --- | --- | --- |
| [#499 governed CAR control loop](https://github.com/periljames/amo-portal/pull/499) | Merged into main on 13 Aug 2026 | **EXISTS** on new branch via main ancestry. Reuse, never cherry-pick duplicate implementation. |
| [#560 external provider platform](https://github.com/periljames/amo-portal/pull/560) | Merged into main on 20 Oct 2026 | **EXISTS** in ancestry; preserve provider identity, tenant boundaries, oversight and Quality notifications. |
| [#562 and #563 Fieldwork/Quality fixes](https://github.com/periljames/amo-portal/pull/563) | Merged 12/16 Oct 2026 | **EXISTS** in ancestry; preserve audit fieldwork/Quality route fixes. |
| [#40 CAR invites and reminders](https://github.com/periljames/amo-portal/pull/40) | Open draft, head codex/integrate-automated-reporting-for-quality-0xinnx; GitHub main comparison: 2 ahead, 8362 behind; not mergeable | **NOT VERIFIED** for its genuinely missing work. Do NOT merge/rebase wholesale. Phase 2: inspect the exact two unique commit patches, then port ONLY features not already in current main with old-versus-new contract tests. |
| [#532 QMS command cockpit](https://github.com/periljames/amo-portal/pull/532) | Open draft | Separate scope; do not absorb unrelated UI routes. |

**Phase 1 actions:** no historical branch merges, no cherry-picks, no application-source edits. Merged legacy work is carried by the up-to-date base branch. Do not claim #40 incorporated: only its history and divergence have been triaged.

## Phase 2 implementation order

1. Recheck current main and PR SHA. Inspect PR #40 changed-file patches and compare with currently active code. Verify all route owners, backend registrations and Alembic graph. Record KEEP/PORT/REJECT per overlapping change.
2. Define minimum tenant-qualified CAR–assurance association, structured investigations, durable draft revision and per-action data, favor existing models; design additive migration and old-CAR backfill. No deletion of legacy results.
3. Implement token-scoped drafts/RCA read-write and authenticated Quality projection with server guards, transactional writes, conflict/idempotency and event history. No public bypass into employee APIs.
4. Implement interactive Fishbone, 5 Whys and CAR-limited Pareto in existing public/internal screens, using a common typed API and accessible fallback.
5. Integrate Quality review, accepted implementation, evidence proof, independent effectiveness, rework, reminders and closure; keep existing CAR number, invite, review and audited history.
6. Harden rate limits, exposure, file handling, DMS/shared storage, API timeouts, responsive layout, link integrity, old data compatibility, retention and restoration. Update ledger with touched paths, code evidence and remaining gaps.
7. Stop at Phase 2 for verification handoff; do not run automated tests/builds/lint/CI manually.

## Phase 3 test and acceptance register

| Gate | Expected verified outcome | Current result |
| --- | --- | --- |
| PostgreSQL migration/rollback and tenant RLS | Existing populated and fresh DB, all head paths, tenant-bound foreign keys, old CARs preserved | NOT VERIFIED |
| FastAPI route contract | Exact public/canonical/auth routes and methods; precedence/alias consistency, no duplicates | NOT VERIFIED |
| Invitation security | Cross-tenant, linked-CAR exposure, revoked/expired/forged/reused token and inaccessible internal APIs | NOT VERIFIED |
| Structured RCA | Branched Five Whys, visual/text Fishbone, factual distinctions, evidence-backed conclusions | NOT VERIFIED |
| Pareto | Authoritative sample, frequency totals, cumulative %, documented sample/filters, persistence | NOT VERIFIED |
| Draft/attachments | Conflict resolution, multi-device saved drafts, retry/idempotency, object-store integrity, failure recovery | NOT VERIFIED |
| CAR lifecycle | Assignment, rejection, recall, action owner/status, independent Quality acceptance, effectiveness, close/reopen | NOT VERIFIED |
| Public/internal real browser | Keyboard, focus, responsive, large record, loading/error/empty, screen reader states | NOT VERIFIED |
| Regression | Existing audit, supplier/provider, register, DMS, notification, backend and frontend suites | NOT VERIFIED |
| CI and PR review | All relevant checks green, skipped gates explained and Codex review findings resolved, no test weakening | NOT VERIFIED |

**Test policy:** Phase 1 intentionally ran no pytest, Playwright, Vitest, lint, typecheck, builds, migrations or manual CI. A GitHub Actions run automatically triggered by the PR is not proof of Phase 3 acceptance.

## End-to-end event chain to preserve

Audit NON_CONFORMITY finding → CAR issuance/assignment/invitation → identity/containment → structured factual root-cause investigation → evidence-linked causal conclusion → individual corrective action plan → Quality review and rework → controlled implementation/evidence → independently verified effectiveness → authorized closure, or reopening/escalation with retained immutable chronology. An accepted *proposal* does not equal completed, verified or effective action.

## Unverified blockers requiring evidence before Phase 2 completes

- Live middleware and PostgreSQL RLS handling for each public-token endpoint; confirmation requires source trace and negative DB tests.
- Intended scope, validity/revocation and proxy/log exposure of related invitation tokens; no production exploit has been demonstrated.
- Existing reusable tasks/owners and supplier/provider authorization scopes; do not create duplicate domain entities.
- Production storage mapping to shared object storage/DMS, recovery and file retention; cannot assert HA from local file paths.
- Current CI failures, migration graph and main movement after the baseline; inspect current data rather than inheriting old PR claims.
- Exact applicable approved MOPM/aviation requirements for case closure and retention; user supplied draft requirements do not establish approval.

See [Phase 1 baseline](CAR_RCA_PHASE1_BASELINE.md) for detailed source references, confirmed API route groups, workflow, historical PR decisions, gap diagnosis and anticipated file changes.

## Phase 2 live implementation reconciliation — 22 October 2026

**Evidence category: SOURCE IMPLEMENTED, NOT TEST VERIFIED.** Source changes are in draft PR #568. The current branch has **90 commits ahead and one main commit behind** as of the latest compare. Reconcile that upstream commit conservatively in Phase 3 after reviewing per-file overlap; no automatic merge was done.

| ID | Phase 2 status | Source evidence and remaining limitation |
| --- | --- | --- |
| F01 | IMPLEMENTED — source, NOT VERIFIED | `car_rca_router.structured_rca_required` and `submit_rca_document` apply the rollout boundary. Legacy narrative responses remain available without fabricated cause nodes; new structured responses require evidence-linked facts and supported causes. |
| F02 | IMPLEMENTED — source, NOT VERIFIED | `CarRcaWorkbench` includes branching 5 Whys, editable Fishbone/category branches, cycle/parent validation, zoom and export; underlying structured nodes are server-persisted and historically versioned. Diagram label/layout and accessibility need real browser verification. |
| F03 | IMPLEMENTED — source, NOT VERIFIED | `car_rca_pareto_router`, `CarRcaParetoSource`, `QualityCarRcaParetoSnapshot` persist tenant-authorized source references, filters, frequency and cumulative percentage for source QMS findings. Respondent-entered counts are labeled separately and are not causal proof. |
| F04 | IMPLEMENTED — source, NOT VERIFIED | Draft `PUT /cars/invite/{token}/draft` with optimistic revision, mutation key, event history and public UI autosave/recovery/conflict. Multiple-device browser concurrency still unverified. |
| F05 | IMPLEMENTED — source, NOT VERIFIED | Scoped guest invite guard, `QualityCarInviteAccessControl`, rotation/revocation/expiry; suppress related-CAR token projection. All old invitation consumers and providers require security testing. |
| F06 | IMPLEMENTED — source, NOT VERIFIED | `QualityCarRcaAction` per-owner/deadline/cause/state, revision, corrective/preventive/containment types, independent internal Quality review, immutable `QualityCarRcaActionEvent`. |
| F07 | IMPLEMENTED — source, NOT VERIFIED | Respondent effectiveness proposals can be adopted into governed `QualityAssuranceCase` / `QualityEffectivenessPlan`; independent reviewer restriction and structured CAR closure gates. End-to-end plan state, reviewers and legacy close paths remain Phase 3-critical. |
| F08 | OPEN WITH REASON | Existing CAR attachments and evidence vault reused, including original links; **shared-object-storage behavior, upload resumability, long-term HA/restore and cryptographic verification were not demonstrated** by the additions. Do not claim these satisfy HA or recovery without infrastructure checks and source changes as needed. |
| F09 | IMPLEMENTED — source, NOT VERIFIED | Specialized routes registered in established Quality router composition; route ordering utility preserves precedence by source design. Runtime FastAPI route identity and duplicate signature test remain open. |
| F10 | IMPLEMENTED — source, NOT VERIFIED | Existing six-step `PublicCarInvitePage` extended with RCA workbench/action controls; internal `CarRecordView` and control-loop operations show corresponding information. Browser keyboard/mobile/large-case pass remains open. |
| F11 | IMPLEMENTED — source, NOT VERIFIED | Historical recall retention introduces `QualityCarResponseRetainedRevision` while leaving active legacy response handling intact. RLS and one-review-inbox acceptance remain unverified. |
| F12 | OPEN WITH REASON | Runtime tenant RLS, provider role gates, delivery truth, shared evidence storage and scale cannot be source-certified. Migrations include tenant isolation/append-only safeguards, but have not been run. |

### Committed application sources

**Backend:** `car_rca_models.py`, `car_rca_router.py`, `car_rca_pareto_router.py`, `quality/__init__.py`, `router.py`, `public_invite_extensions.py`, `car_control_loop_guard_router.py`, `assurance_case_router.py`.  
**Schema:** `backend/amodb/alembic/versions/quality_20261022_car_rca.py`.  
**Frontend:** `PublicCarInvitePage.tsx`, `CarRecordView.tsx`, `QmsCarControlOperations.tsx`, `qmsCore.ts`, `qmsCarRca.ts`, and six focused UI/style components under `frontend/src/components/QMS/carRca/`.

**Compatibility:** no duplicate authoritative CAR register; original issued links honored except explicitly revoked/expired; controlled new-record rollout; legacy text untouched; Quality approvals independent from guest input. Prior PR #40's obsolete router diff was not merged wholesale. Prior merged features remain in branch ancestry.

**Phase 3 is the first permitted execution of** pytest, Vitest, Playwright, lint, typecheck, frontend build, migrations, PostgreSQL negative tenant tests and end-to-end report/attachment/closure tests. No source-only entry above is a claim that those checks passed.

**Important:** Phase 2 source still needs final focused source-level closure and evidence-storage integration review; F08 and F12 are not accurately described as completed until that source or operational proof exists. Do not merge PR #568 before resolving them and Phase 3.

### Additional Phase 2 source hardening after reconciliation

- The Fishbone/Five Whys editor now blocks selecting a node's own descendants as parents before a cycle reaches the backend. Server-side graph validation remains authoritative.
- The public RCA workbench now links previously uploaded CAR attachments by stable `CAR-ATTACHMENT:{id}` reference rather than requiring duplicate uploads. Backend verification checks that those referenced files actually belong to the exact CAR at structured RCA submission, corrective-action proposal, and implementation progress.
- Existing non-CAR controlled evidence references remain narrative/record references subject to independent Quality review; they are **not** represented as cryptographically verified uploaded files.
- **Remaining Phase 2 source concern:** evidence upload itself still uses the established storage mechanism. Platform-wide shared object-store migration, resumable uploads, failover and restore are not established by these changes. These must not be represented as delivered unless separately implemented/verified.

### Remaining Phase 2 closure blockers

- Shared CAR storage adapter exists but its integration into the legacy CAR router is not committed; no statement of object-storage readiness is warranted.
- Serialized draft saves and CAR evidence-link UI changes need repository updates and validation.
- Do not merge until these integration issues and Phase 3 checks are resolved.
