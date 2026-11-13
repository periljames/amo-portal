# AMO Portal Enterprise QMS/DMS — Source and PR Reconciliation Baseline

**Observed:** 2026-11-11 (GitHub connector, live repository metadata and selected source inspection).  
**Target:** `main`; **observed main HEAD:** `86a66d2d3630518a67ff3f02d5c9467cdcdfd90d` (commit dated 2026-10-27).  
**Consolidation branch:** `feat/enterprise-qms-dms-consolidation-20261111`.  
**Phase:** 1 — investigative baseline; this file does **not** certify implementation or production acceptance.

## Evidence standard

`COMPLETE` = specifically evidenced committed implementation and appropriate acceptance; `PARTIAL` = a real sub-capability is present but lifecycle/acceptance remains incomplete; `DEFECTIVE` = demonstrated failure; `MISSING` = confirmed absent in the inspected canonical owner; `SUPERSEDED` = replaced by demonstrably newer canonical code; `NOT VERIFIED` = claims, source presence, and/or tests not sufficient to establish operation. Branch-local implementation does not imply mainline availability. GitHub metadata, source inspection, CI results, and live operating acceptance are separate evidence tiers.

## Verified repository and PR state

Repository: https://github.com/periljames/amo-portal . `main` resolves to `86a66d2d3630518a67ff3f02d5c9467cdcdfd90d`; no enterprise consolidation baseline file existed at that HEAD. GitHub reported 34 open PRs when queried. Review or CI status may change after this snapshot; always refresh before decisions.

| PR | Live status / relationship to main | Reconciliation disposition |
| --- | --- | --- |
| #564 Venspera readiness | OPEN DRAFT; `463fdeff5feb8404f9baa97044ce57f880832cec`; ahead 246, behind 0, mergeable | **PARTIAL / external ownership.** Owns platform security, storage, tenant/account/production hardening. Do not absorb entire 92-file platform PR. Isolate necessary adapters and coordinate file-level shared changes; current-head CAR real-browser CI failure observed. |
| #569 Word/365 | OPEN DRAFT; `4fb9536d07588fcb7048e962f7455f15222695cf`; ahead 12, behind 0, mergeable | **PARTIAL branch-only.** 25 files: source-linked PDF renditions, controller verification, Microsoft Graph mapping and UI. No equivalent Microsoft routes or rendition model in inspected main. Source is untested; several workflows reported failed on branch HEAD. Port coherently then verify; never silently claim Word-identical output. |
| #557 company library | OPEN DRAFT, not mergeable; `46eb2396335482a2793e95233a5fc5d16e40dbd3`; diverged, 46 ahead / 1321 behind | **PARTIAL branch-only.** Unique favorite column/migration, saved views, search, presentations and intake components. Main already has library/discovery routers; merge surgically and retain newer mainline guards and metadata. |
| #558 binding authority | OPEN, not mergeable; `ab2720395ecbf66ec344664b2f546c200f3ecf4e`; diverged, 47 ahead / 1321 behind | **PARTIAL branch-only.** Unique paginated binding list with authoritative `total`, exact-ID read and full lineage route; route ordering/frontend consumers must be reconciled. Main currently exposes `/audits/{audit_id}/checklist-bindings` with a 100-row limit. Reconcile carefully with current route ordering, preserving `checklists/parse-upload` handling. |
| #554 auditor workflow | MERGED 2026-10-09 | **PARTIAL** as to programme acceptance: existing canonical audit, offline and fieldwork foundation; reverify in consolidated HEAD. |
| #568 CAR/RCA | MERGED 2026-10-27 | **PARTIAL** as to release: current CAR/RCA source and history foundation; user-specified real-browser failure still requires Phase 3 reproduction. |
| #540 People frontend; #537 quality regression; #534 DMS CSS; #532 audit cockpit; #520 resolver; #512 audit hardening; #353 quality war room; #40 CAR invites | OPEN, generally divergent/nonmergeable | **NOT VERIFIED** unique live-branch value. Compare individual file changes with current main; do not reintroduce older router/UI state. |
| #290 compliance authorization; #280 e-signatures; #519 AI gateway | OPEN, platform/cross-cutting | **NOT VERIFIED** safe QMS/DMS overlap; retain module ownership; optional integration only if necessary and independently validated. |
| #479 OEM MPD; #484 AMP overlay; #442 planning release; #278 Planning/Production; #452 user directory | OPEN, principally external ownership | **NOT VERIFIED** integration dependency; do not import wholesale. For #484, its base is #479 rather than main. |
| #560 external-provider platform; #563 post-merge repair | MERGED 2026-10 | **PARTIAL** existing cross-module foundation; avoid overwriting their interfaces with older QMS PRs. |

Additional open PRs discovered: #569, #564, #558, #557, #549, #540, #537, #534, #532, #528, #520, #519, #512, #487, #484, #479, #455, #452, #446, #442, #441, #439, #435, #434, #431, #393, #383, #355, #353, #290, #280, #278, #71 and #40. Non-QMS changes are excluded unless a measured contract dependency requires them.

### Canonical ownership in inspected main

| Area | Source and live ownership | Observation |
| --- | --- | --- |
| Quality router composition | `backend/amodb/apps/quality/__init__.py`, `canonical_router.py`, `canonical_core_router.py` | Existing special-purpose routes must precede generic `/{module_path:path}` handlers; do not add parallel approval engines. |
| Audit binding | `audit_checklist_template_router.py`, `audit_checklist_template_route_order.py`; instantiated audit checklist in `audit_checklist_execution_router.py` | Main has governed template/binding models and a bounded 100-row listing, but not branch #558's direct-ID/lineage contract; maintain exact stored source context. |
| CAR/RCA | `car_control_loop_*.py`, `car_rca_router.py`, `car_rca_pareto_router.py`, `car_feedback_router.py`, `models.py` | Preserved current mainline source; a successful response commit/read must be tested as a transaction, not merely a browser assertion. |
| DMS | `backend/amodb/apps/doc_control/router.py`, `workspace_library_router.py`, `workspace_library_discovery_router.py`, `workspace_service.py`, `backend/amodb/apps/manuals/{models,router}.py` | Existing seven-workspace control model, governed revisions, library and publication reader must remain authoritative. |
| DMS frontend | `frontend/src/pages/documentControl/`, `frontend/src/services/documentLibrary.ts`, `frontend/src/pages/manuals/` | Preserve library, physical custody, distribution, records and PDF.js. Branch #557 and #569 change overlapping pages/models. |
| Shared | `backend/amodb/security.py`, `storage.py`, `alembic/env.py`, Accounts, Platform, Training, Procurement | Changes require scoped migration/security review and coordination with #564. |

### Migration collision map

Main already contains `quality_car_feedback_261027` (verify actual Alembic graph at runtime). #569 adds `docx_fidelity_261028` (down revision `quality_car_feedback_261027`) then `doc_m365_261028` (down revision `docx_fidelity_261028`). #557 adds `docctl_261009_favorites` with down revision `quality_261003_evidence_context`. #564 adds storage migrations plus schema-neutral `venspera_quality_261029_merge` with parents `plat_261026_merge_heads` and `quality_car_feedback_261027`. **Do not invent a clean single head:** inspect graph and deploy history, add a justified schema-neutral merge revision if needed. Changes to `manuals/models.py` from #557 and #569 are additive but must be composed together, not overwritten. #564's `env.py` and storage integrations require separate integration planning.

## Mainline functional maturity, evidence and severity

The dated live gap review `docs/qms-live-gap-review-2026-10-22.md` explicitly distinguishes page loading from completed processes. It reports that 43 settled shared register destinations loaded but specialist flows below had not been demonstrated. Confirmed operational gaps are therefore **PARTIAL**, not automatically `MISSING`. These are P0 when a missing guard can lead to unauthorized publication/closure or unsafe equipment use; P1 for essential lifecycle completion; P2 for presentation/efficiency.

| Workstream | Status | Priority | Source evidence and next verification |
| --- | --- | --- | --- |
| DMS Office reader fidelity and revision-bound rendition | PARTIAL (branch #569 only) | P0 | Main `manuals/models.py` lacks `ManualRendition`; #569 adds rendition model/router, reader changes and migration. Confirm Word-exported PDF source checksum, publication blocker, privileged upload and exact read path. |
| Optional Graph/SharePoint working-file bridge | PARTIAL (branch #569 only) | P0 | Main `doc_control/router.py` lacks Graph wiring; #569 adds models/router/service/UI. Consent, OAuth state, token lifecycle, eTag races, safe redirects, tenant isolation and disconnection are NOT VERIFIED. |
| Company library workflow | PARTIAL | P1 | Main has library/discovery; #557 adds saved shared views, favorites and UI. Reconcile main metadata, permissions, sorting, pagination and reader bookmarks. |
| Audit binding authority/lineage | PARTIAL | P0 | Main binding endpoint capped at 100; #558 adds bounded list + total, exact confirmation and lineage; must test >100 and frozen fieldwork. |
| CAR/CAPA closure and transaction correctness | PARTIAL / CI DEFECTIVE (#564 HEAD) | P0 | #568 merged structured RCA; #564's HEAD has QMS CAR real-browser failure. Reproduce run 41999293028 and distinguish its commit from consolidation HEAD; no mock/skip. |
| Risk and opportunities | PARTIAL | P1 | Live-gap review says matrix/register views not authoritative assessment/acceptance; verify SMS vs Quality ownership before schema design. |
| Management review | PARTIAL | P1 | Main `frontend/src/services/qmsManagementReview.ts` and shared review views exist; complete documented decisions, sign-off, action closeout, source-backed inputs. |
| Equipment and calibration | PARTIAL | P0/P1 | Main has `qmsEquipment.ts`, source-backed read views; acceptance of certificates, quarantine/out-of-tolerance and Stores/equipment authority NOT VERIFIED. |
| System/process control | PARTIAL | P1 | Register/scope/objective views exist; owner, KPI, controlled review/actions not demonstrated. |
| Regulator/customer interface | PARTIAL | P1 | Distinguish external auditor draft-finding promotion already in audit from regulator/customer correspondence and commitment tracking; avoid duplicates. |
| Reporting intelligence | PARTIAL | P1 | `reports_router.py` implements bounded CSV/HTML report snapshots; several QMS named views still use generic register rather than specialist trends. No invented compliance KPI. |
| Training/acknowledgement/revision triggers | NOT VERIFIED | P0/P1 | Document acknowledgements and training records exist; exact governed revision → assignment/acknowledgement transaction must be traced end-to-end. |
| Supplier eligibility | PARTIAL | P0 | Procurement owns supplier commercial record; Quality provider qualification/oversight exists. Must show approved/suspended state gates purchasing without creating shadow copies. |
| Personnel authorization | PARTIAL | P0 | Quality People/authorization routers exist; tenant, qualifications, expiry and assignment enforcement must be demonstrated at transaction boundary. |
| Storage, retention, recoverability | PARTIAL (#564 branch) | P0 | Main has local/shared storage abstractions; #564 adds S3 quota/physical ledger and controls. Live restore, multi-node, PostgreSQL RLS and deployment evidence not yet available. |

## End-to-end workflow acceptance contract

Every in-scope flow must demonstrate **Initiate → Assign → Execute → Evidence → Review → Approve → Publish/Implement → Distribute → Acknowledge → Verify → Close → Retain → Prove** as applicable. Each step needs (a) visible permitted action, (b) tenant-scoped API mutation, (c) durable persisted authoritative state, (d) named actor/time and evidence, (e) correct rejection of forbidden or stale transitions, (f) reconstruction from source history. Not every workflow has every stage; document the justified applicability and avoid artificial approvals.

## Sequencing and preservation controls

1. Preserve mainline PDF.js, governed manuals, current CAR/RCA/Fishbone/Five Whys/Pareto, audit offline commands, provider identity and planner corrections.
2. Integrate source-correct #569 DMS bridge (no automatic Word publication); compose additive #557 library primitives with branch #569 and newer main.
3. Port #558's authoritative binding read and lineage **without** copying its 1321-commit-stale branch.
4. Complete existing specialist QMS flows behind their canonical owners, typed IDs and permission-aware links.
5. Treat #564 platform as an externally owned prerequisite: share a scoped integration contract, not a wholesale 92-file merge.
6. End Phase 2 with implementation ledger and prepared tests; Phase 3 re-checks main HEAD, runs actual upgrades/contracts/browsers/CI and records blockers.

## Evidence limits

This baseline relies on GitHub metadata, selected source, dated documented live reviews and branch CI conclusions. It **does not** include a checked-out running backend, working database, authentication fixture, rendered screenshots, Graph tenant consent, KCAA legal verification, complete migration graph execution or physical disaster-recovery test. Those are NOT VERIFIED. GitHub PR descriptions and historical CI assertions are not independent acceptance. Refreshed state and exact code-level review are required before each port.

## Older PR file-level reconciliation — continuation (2026-11-11)

Verified each PR's current live state and changed-file inventory against main; **none of the below stale branches was merged wholesale**. Source presence in main is not proof of acceptance.

| PR | Material diff families | Decision / canonical owner |
| --- | --- | --- |
| #534 | DMS workspace theme token and library chip overflow, two CSS files | **PARTIAL UNIQUE → PORTED**: theme-adaptive muted surface and wrapping category filters applied to current `documentControlWorkspace.css` and `documentLibrary.css`. No wholesale old CSS replacement. |
| #512 | archive package preflight on evidence-input size and PostgreSQL INTEGER package-size bounds, older archive-route wrappers | **PARTIAL UNIQUE → PORTED** size checks **directly** into current `audit_archive_package_router.py`, preserving current route composition/cleanup. Its monkeypatch/route-order version was not imported. |
| #540 | People frontend search/rail/dialog accessibility, semantic checks | **PARTIAL / NOT VERIFIED** distinct details: main already has 1335-line People authorization workspace, active personnel detail and governed authorization actions; 8 of 12 old UI hunks do not apply to main, indicating significant divergence. Do not overwrite current People UX without verifying individual behavior. |
| #537 | checklist/report/role regression checks across quality and frontend | **PARTIAL / NOT VERIFIED** old branch touches 44 files, including real auth and audit permission modules. Current main has newer audit execution, RCA, QMS roles and route composition; preserve main, use the still-relevant negative tests during Phase 3 rather than sweeping older patches. |
| #532 | old standalone audit command-search router and cockpit UI | **PARTIAL / NOT VERIFIED** old `command_search_router.py` absent main; main has `QmsCommandPalette.tsx` and current Audit Assurance Dashboard. Determine exact useful command/search semantics via Phase 3, avoiding duplicate command engine. |
| #520 | audit resolver/personnel API alignment | **PARTIAL / NOT VERIFIED** main retains `qmsAuditOccurrenceResolver.ts` and later operational route-order fixes; older branch is divergent. Test exact authoritative resolver & personnel transaction paths before deciding on additional port. |
| #353 | older independent Quality war-room/audit lifecycle engine | **SUPERSEDED architectural proposal, NOT VERIFIED each historical feature**: main retains newer canonical Audit Programme, Prepare, Live execution, fieldwork, archive and CAR engines. Do not create another `audit_lifecycle` engine. |
| #40 | pre-modern CAR invites, enum/model/router/service/UI modifications | **SUPERSEDED architectural proposal, NOT VERIFIED every old detail**: current CAR public-invitation and control-loop routes from merged #568 are canonical. The ancient branch must not replace them. |
| #290 | platform authz, audit ledger and training gates | **NOT VERIFIED** safe mainline overlap; refer security ownership to #564. QMS-specific guard checks may become acceptance tests, not platform wholesale import. |
| #280 | E-signature platform capability with many migrations | **NOT VERIFIED / external owner**; controlled approvals in QMS/DMS do not assume external e-signatures exist or have regulatory validity. |
| #519 | AI gateway/assistant runtime | **NOT VERIFIED / external owner**; existing Document Control assistant remains supplemental and cannot approve or publish. |
| #479/#484 | OEM MPD governance and AMP (with #484 targeting #479, not main) | **NOT VERIFIED / external owner**; QMS links typed source identity only after OEM/AMP owner is merged/approved. |
| #442/#278 | Planning/Production migrations, approvals, execution | **NOT VERIFIED / external owner**; no shadow planning or execution code imported. |
| #452 | identity/user administration changes | **NOT VERIFIED / external owner**; current account and People permission sources remain authoritative. |

**Risk acceptance hardening after initial baseline:** existing risk backend had allowed any declared rating to be selected independently of the likelihood/consequence pair; this did not establish a governed tenant matrix. The consolidated code now enforces complete `rating_cells`, revision-aware edits, server-calculated rating correctness and rejection of stale residual acceptance, while retaining a snapshot of the exact assessment matrix. No tenant matrix, threshold or compliance approval was fabricated.

**Management review attendance:** invitations do not prove attendance. The specialist review now records a self-attested, timestamped, tenant-scoped presence/absence decision and blocks submission if none of the invited participants confirmed presence.

**Storage/governance boundary:** #564 remains externally owned. Only needed shared inspection/control changes are in this PR. No platform readiness or disaster-recovery claim is made without on-environment proof.
