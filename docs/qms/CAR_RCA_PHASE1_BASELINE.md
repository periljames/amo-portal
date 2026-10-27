# QMS CAR / RCA — Phase 1 source baseline

**Repository:** `periljames/amo-portal`  
**Dedicated branch:** `feat/qms-car-rca-unified-20261022`  
**Baseline main SHA (before this documentation):** `75ab74c34422732f175d17cdae2acdb1879a1146`  
**Baseline tree:** `f722cd3455a7eb7dce202dfc1aa9e42a6d1e0a4a`  
**Observed baseline commit:** 22 October 2026, 07:06:43 UTC, “Fix vendor entry and register QMS account governance workspace.”  
**Assessment date:** 22 October 2026. **Assessment type:** GitHub source review; NOT a deployed/browser/runtime security assessment.

## Scope and nonnegotiable invariants

This feature is **an additive, backward-compatible enhancement** to existing QMS CAR, audit findings, external invitations, Assurance Cases, evidence and effectiveness controls—not a new CAR application. Continue on this branch/PR for Phase 2 and Phase 3. Never merge into `main` without reviewed changes, verified migrations, security checks and passing acceptance. Phase 1 changed documentation only; no pytest, browser suites, Vitest, lint, typecheck, builds, migrations or CI manually executed. Automatic GitHub checks, if triggered, do not establish acceptance.

**Statuses:** EXISTS = present in inspected source; PARTIAL = functional elements exist but not end-to-end; MISSING = no implementation found in the identified authoritative path; DEFECTIVE = observed design/code shortcoming; NOT VERIFIED = not proven without further inspection/runtime check. These statuses **do not** certify behavior in production.

## 1. Registered frontend route and dependency map

| Entry | Resolution verified in source | Status |
| --- | --- | --- |
| `/car-invite?token=...` | `frontend/src/portalRoutes.tsx:512` loads `PublicCarInvitePage`; `qmsCore.ts` public client uses `/quality/cars/invite/{token}` | EXISTS |
| `/qms/car-access/:token` | `frontend/src/App.tsx:37,106-108` intercepts before `AppRouter`; `CanonicalPublicCarAccessPage.tsx` adapts to the **same** invite page | EXISTS |
| `/maintenance/:amoCode/quality/cars` and register scopes | `portalRoutes.tsx:831-839` → `QmsCanonicalPage.tsx:56-66` → register/control-loop page | EXISTS |
| `/maintenance/:amoCode/quality/cars/:carId/*` | `portalRoutes.tsx:840` → `QualityCarsPage` / `CarRecordView` | EXISTS |
| `?control={carId}` | `QmsCanonicalPage.tsx:56-59` delegates to `QmsCarControlLoopPage.tsx` and `QmsCarControlOperations.tsx` | EXISTS |
| `/maintenance/:amoCode/quality/audits` | Canonical QMS routing; finding creation/review and CAR linkage remain in original Quality ownership | EXISTS |
| RCA internal workspaces | `QmsAssurancePage.tsx`, `analysis/AnalysisInvestigation.tsx`, `analysis/AnalysisQuantitative.tsx` | EXISTS, but separate from public CAR |

Role-gated canonical CAR routes use `RequireAuth` and `RequireQmsPermission` (`qms.car.view`); public invite routes intentionally bypass employee login. `App.tsx` delegates canonical guest CAR access before the regular authenticated app. Styling includes `car-invite.css`, `car-invite-responsive.css`, plus dynamically loaded responsive overrides in `QualityEnhancementsHost.tsx`; do not introduce competing global styles or second page engines. Route matching/overlays, keyboard navigation, real mobile behavior and large-upload rendering require Phase 3 browser verification.

**Frontend clients:** `qms.ts` re-exports `qmsCore.ts`; `qmsCarInviteDraft.ts` owns browser-only draft; `qmsCarControlLoop.ts` and `qmsCarControlEvidence.ts` own the control-loop projection; `qmsAssuranceCases.ts` owns investigation/effectiveness API; `qmsAnalysis.ts` retrieves quantitative evidence; `qmsRegisters.ts` retrieves paged CAR register; `apiClient.ts` owns authenticated request timeouts/cache/idempotency features. `qmsAuditExternalAccess.ts` has its own guest-audit session protocol and should **not** be confused with public CAR token authorization.

## 2. Backend source owners and route precedence

The authoritative CAR table is `quality_cars` in `backend/amodb/apps/quality/models.py:827-934`; CAR responses, actions, and attachments are `quality_car_responses`, `quality_car_actions`, and `quality_car_attachments` (same module). `router.py` is the existing CAR state machine and audit-finding link. `service.py` generates tenant-scoped CAR numbers/invite tokens. Public token GET/PATCH are **replaced**, not duplicated, by `public_invite_extensions.py:273-279`, which retains base submission validation/notifications via delegation; the base `public_router` owns recall/attachments/history/report routes.

Canonical tenant aliases are cloned from legacy CAR handlers with `resolve_tenant_context` by `car_operational_route_order.py:35-96`; control-loop guarded routes use `car_control_loop_guard_router.py`, `car_control_loop_authority_guard.py`, `car_control_loop_evidence_guard.py`, and explicit route promotion in `car_control_loop_route_order.py`. `quality/__init__.py:198-242` composes these **before** generic catch-alls. Do not register a duplicate handler or bypass the canonical resolver. Actual runtime route matching is NOT VERIFIED until Phase 3.

**Confirmed API families from decorators and adapters:**

| Access | Verb | Handler/contract |
| --- | --- | --- |
| Public | GET, PATCH `/quality/cars/invite/{token}` | Extension GET; extension PATCH delegates to base submission |
| Public | POST `/quality/cars/invite/{token}/recall` | Base public router |
| Public | GET, POST, PATCH, DELETE attachment subroutes; GET actions, form, audit-report | Base router / extension; preserve scoped semantics |
| Tenant | POST, GET `/quality/cars`; PATCH `/quality/cars/{id}`; POST `/quality/cars/{id}/review` | CAR lifecycle, role/assignee/reviewer guards |
| Tenant | GET `/quality/cars/register`; evidence-pack, print, responses, actions, reminders, escalation, extension requests | Existing register and dependent families |
| Tenant canonical | `/api/maintenance/{amo_code}/quality/cars[...]` | Alias of guarded existing CAR handlers; preserve precedence |
| Tenant canonical | GET/PATCH/POST `.../cars/{car_id}/control-loop[...]` | Control profile, milestones, dependencies, deadlines, evidence, evaluation/closure |
| Tenant canonical | GET, POST `.../assurance-cases`; GET `.../{case_id}`; POST `.../{case_id}/transitions`, `.../{case_id}/investigation`, `.../{case_id}/effectiveness-plans` and `.../conclusion` | Assurance Case lifecycle; `qms.audit.manage` to append investigation; `qms.car.manage` for effectiveness |
| Tenant canonical | GET `.../analysis/snapshot` | `qmsAnalysis.ts` authorized finding-level aggregate; verify backend implementation and population independently |

Exact nested route promotion and HTTP-level authorization need Phase 3 route inventory assertions. Do not treat all API families as accessible to the public auditee.

## 3. Source-of-truth database and backward compatibility

- `quality_cars`: tenant `amo_id`, CAR number/program, finding FK, current narrative, invite token, statuses, reminder data, due dates, current review flags and evidence summary. Existing data and IDs are **immutable business identifiers**, not migration targets to regenerate.
- `quality_car_responses`: submitted response records; status/review provenance, with current code handling recalled submissions.
- `quality_car_actions`: attributable CAR action/comment/state chronology.
- `quality_car_attachments`: file reference, content type, size, SHA-256 and CAR link. `router.py:116-118` currently uses a generated local attachment directory; storage/shared-object guarantees must be verified before assuming HA.
- `quality_car_control_profiles`, `quality_car_milestones`, `quality_car_dependencies`, `quality_car_deadline_changes`, `quality_car_control_events`: governed stage and closeout data (`car_control_loop_models.py` and migration `backend/amodb/alembic/versions/quality_260811_car_loop.py`).
- `quality_assurance_cases`, `quality_investigation_entries`, `quality_effectiveness_plans`, `quality_assurance_case_events`: independent assurance evidence/analysis records (`assurance_case_models.py` and migration `backend/amodb/alembic/versions/quality_260808_assurance_cases.py`). Investigation entries already have method, FACT/HYPOTHESIS/CAUSAL_CONCLUSION, parent, category, confidence, evidence refs and creator. Migration installs PostgreSQL tenant RLS and append-only controls on relevant records.
- `qms_corrective_actions`: **legacy/coexistence-only**, explicitly guarded in `router.py:7454-7489`; do not resurrect as a second authoritative CAR engine.

**Phase 2 schema strategy (proposal, not implemented):** introduce only minimal tenant-qualified CAR↔assurance-case association, server draft/revision and item-level corrective action tables where existing structures cannot safely represent requirements; verify the live Alembic head graph first. Use additive nullable/default-safe columns/tables, composite tenant guards/indices, deterministic idempotent backfill from existing CAR narrative, read fallbacks and reversible downgrade where safe; do not rewrite old submitted responses, delete audit trails, migrate original attachments destructively or change existing status values. Explicitly map all pre-control-loop CARs. Protect append-only history with new immutable events, not destructive edits.

## 4. Observed lifecycle and actors

```text
Auditor finding (NON_CONFORMITY) --create--> quality_cars CAR
    -> assign + notify/email invite -> public response
    -> containment + narrative RCA + narrative corrective/preventive plan + evidence
    -> PATCH invite: reviewable CARResponse, status PENDING_VERIFICATION
    -> Qualified Quality reviewer evaluates RCA and CAP separately:
        REJECTED / NEEDS_EVIDENCE -> in-progress rework
        ACCEPTED + ACCEPTED -> IN_PROGRESS (NOT CLOSED)
    -> controlled milestones: RCA_SUBMISSION / CAP_APPROVAL /
       IMPLEMENTATION_COMPLETE / EVIDENCE_COMPLETE / EFFECTIVENESS_REVIEW
    -> guarded implementation/evidence review + independent effectiveness
    -> explicitly authorized closeout -> CAR CLOSED + finding closure
    -> post-close record locked; formal reopening behavior remains to be verified
```

Sources: `router.py:5998-6083, 6630-6717, 6872-7004, 7560-7663`; `car_response_workflow.py:11-47`; `car_control_loop.py:316-372`. **Established safeguard:** root cause/CAPA acceptance by itself does **not** close the CAR: `router.py:6657-6669` keeps it IN_PROGRESS. Control-loop close readiness requires accepted/completed milestones, appropriate evidence and resolved blocking dependencies. Reviewer-authority, deadline-extension and evidence guards exist. **Not verified:** runtime independent-review enforcement for every transition, effectiveness treatment for optional cases, cross-workflow reopen, and provider-account delegation.

## 5. Confirmed findings, symptoms, source causes and priorities

| ID | State / priority | Source evidence | Action required |
| --- | --- | --- | --- |
| F01 | **DEFECTIVE / P0** | `PublicCarInvitePage.tsx:645-659, 765-772` only asks for nonempty `root_cause`; `router.py:6913-6920` validates narrative/evidence existence, not a structured causal chain | Add tenant-aware structured RCA contract, evidence-linked conclusions and submission-ready validation; preserve legacy fallback for previously completed CARs |
| F02 | **PARTIAL / P0** | `AnalysisInvestigation.tsx:57-71` shows method dropdown, category and parent select; no Fishbone SVG/canvas drawing and no guided branching 5 Whys in this inspected component | Reuse `quality_investigation_entries` for real editable/accessible visualizations, not mere method labels; keep append-only persistence |
| F03 | **PARTIAL / P0** | `AnalysisQuantitative.tsx` renders a Pareto of authorized aggregate finding requirements from `qmsAnalysis.ts`; no public CAR-specific Pareto submission | Add bounded, authorized CAR-scoped Pareto/evidence selection and saved analysis snapshot with sample size, period and caveats; no unscoped tenant data to invite token |
| F04 | **DEFECTIVE / P0** | `qmsCarInviteDraft.ts:19-45` stores draft in `sessionStorage` by CAR ID, drops it if serialized current server fields differ | Create durable **server** draft/revision with optimistic concurrency, scoped guest token, merge/recovery and explicit conflict UI; migrate session drafts safely and never leak tokens into persisted draft |
| F05 | **PARTIAL / P0 security review** | `router.py:6768-6800` returns up to 25 related CARs' **invite tokens** scoped by tenant/audit/assignee, then `PublicCarInvitePage.tsx:700-707` auto-opens them. `quality_cars` has invite token but no explicit expiry/revocation column | Prove intended grant for **each** related CAR; stop transitively granting bearer URLs without explicit authorization. Design scoped expiry, revocation, rate limits, throttled access; investigate all public attachment/history paths. Actual exploitability NOT VERIFIED |
| F06 | **PARTIAL / P1** | Existing `quality_car_milestones` track stages but `quality_cars` stores singular corrective-action narrative; `quality_car_dependencies` track blockers, not individual auditee action completion | Introduce real per-action owner/due/evidence/implementation/review if no authoritative task entity can serve. Avoid duplicate task engines |
| F07 | **PARTIAL / P1** | `quality_effectiveness_plans` carry expected outcome, measure, reviewer/date and conclusion evidence; CAR control milestones have effectiveness stage | Bind each accepted RCA/actions to scheduled independent check; rejection/ineffectiveness triggers rework, no silent closure. Compare with existing `effectiveness_response_router.py` |
| F08 | **PARTIAL / P1** | `router.py:116-118, 7322-7360` saves local file path and metadata; public/tenant upload workflows exist | Validate file types, signed downloads, failed upload retry, upload/database atomicity, dedup/quotas, DMS/object-storage durability; live deployment and migration NOT VERIFIED |
| F09 | **PARTIAL / P1** | `public_invite_extensions.py:273-279` rewrites public GET/PATCH route; `car_operational_route_order.py` clones tenant handlers; catch-all handlers promoted | Add route uniqueness/precedence and old-vs-new URL contract tests before modifying router order |
| F10 | **PARTIAL / P1** | `QmsCanonicalPage`, `QualityCarsPage`, `QmsCarControlLoopPage` are different projections of one CAR | Unified navigation/read model, consistent loading/error/empty state, accessible stepper, focus, responsive layout and large-file resilience; verify in real browser |
| F11 | **PARTIAL / P1** | Existing `CARResponse` + `CARActionLog` and append-only Assurance Cases record chronology; `router.py:6922-6928` deletes recalled, unreviewed submitted response | Define retention/immutable revisions and rework trail so a replaced response cannot remove evidentiary provenance |
| F12 | **NOT VERIFIED / P1** | All invitation endpoints, route dependencies and tenant context were inspected only as source | Prove cross-tenant and cross-provider isolation, same-CAR concurrent edits, expiry/replay, independence, upload errors, perf and actual email acknowledgment in Phase 3 |

## 6. Existing capabilities that must not regress

Audit/finding issuance and link; CAR numbering; direct and canonical invitation URLs; approved-report downloads; response count/recall lock after review opened; evidence upload and server checksums; status transitions; separately reviewed RCA/CAPA; Quality-authorized decisions; email/reminders/escalations; no automatic closure on plan acceptance; control-loop milestones, dependencies and deadline extensions; tenant role controls; RLS and immutable assurance events; external-provider account/QMS connections already landed in main; independent effectiveness outcome and historical reporting; REST clients, caching, UX and responsive styles. All CAR IDs, recorded texts, status history and external links must remain usable.

## 7. Earlier work / cautious consolidation decision

**Merged and already in baseline main:** PR [#499](https://github.com/periljames/amo-portal/pull/499) (CAR control loop), PR [#560](https://github.com/periljames/amo-portal/pull/560) (external-provider platform), and PRs [#562](https://github.com/periljames/amo-portal/pull/562) / [#563](https://github.com/periljames/amo-portal/pull/563) (Fieldwork/Quality repairs). Reuse these implementations **as present on main**; do not cherry-pick historical commits already incorporated.

**Unmerged:** PR [#40](https://github.com/periljames/amo-portal/pull/40) “Enhance CAR invites and reminders” remains open. GitHub comparison against the documented baseline reports branch **2 commits ahead, 8362 behind, diverged, not mergeable**, with overlapping `router.py`, CAR models/schemas and invite UI. Its objectives (tokens, reminders, public invite) have substantial counterparts in current main. **Do not merge #40 wholesale, force-rebase, or copy obsolete route handlers.** In Phase 2 examine its exact two unique commits/patches for genuinely missing behavior, port only needed changes surgically, and record rejected duplicates. Open draft PR [#532](https://github.com/periljames/amo-portal/pull/532) modifies QMS command workspace; do not fold unrelated UX changes into CAR work. This Phase 1 has merged **no other branches** and modified **no application source**.

## 8. Phase 2 implementation order and anticipated files

1. Recheck main SHA/PR concurrency, source/route ownership, old PR #40 unique diffs, Alembic graph and controlled feature flag/fallback.
2. Design and migrate tenant-qualified CAR-assurance relation, immutable response revisions, durable drafts and per-action data only where necessary: `backend/amodb/alembic/versions/<verified_next_revision>.py`; `models.py`, `assurance_case_models.py`, optional focused additive `car_rca_models.py`.
3. Implement scoped guest RCA/draft endpoints in **existing** `public_invite_extensions.py`; strict tenant/actor/deadline rules in `router.py`, `car_control_loop_*.py`, `assurance_case_router.py`, `tenant_security.py` if necessary; update `quality/__init__.py` and route promotion only after checking duplicates.
4. Add canonical API DTOs in `schemas.py` / focused schema module; adapt `qmsCore.ts`, `qmsCarInviteDraft.ts`, `qmsAssuranceCases.ts`, `qmsCarControlLoop.ts`, `qmsAnalysis.ts`, `apiClient.ts` without a second client or state machine.
5. Build shared, keyboard-accessible editable Five Whys/Fishbone/Pareto visual workspace within `PublicCarInvitePage.tsx` and internal `AnalysisInvestigation.tsx`, `AnalysisQuantitative.tsx`, `QmsAssurancePage.tsx`; add focused components under `frontend/src/components/QMS/carRca/` only if warranted. Retain existing responsive layout and invite page.
6. Integrate per-action statuses, evidence, Quality review and effectiveness, rejection/resubmission, notifications and reports in existing CAR/control-loop screens; retain legacy projections and CAR evidence packs.
7. Reconcile backfill, old CAR read-only behavior, effective permissions, DMS/storage behavior and source-level TypeScript/Python contract consistency. **Do not run test/build/lint/CI in Phase 2 per instruction.**

**No exact new migration filename or endpoint shape may be finalized before source/migration compatibility review.** Planned files are proposals, not claims of existence.

## 9. Phase 3 tests, cleanup and go/no-go

| Gate | Acceptance |
| --- | --- |
| DB/Alembic | Clean and already-populated Postgres upgrade/downgrade, RLS and tenant FKs, all current heads, no loss of 2026 records |
| Route contract | Public original/canonical routes, legacy aliases, static-before-catchall, method ownership, no duplicate route shadowing |
| Guest authorization | Expired/revoked/replayed/wrong-token, related-CAR leakage, unauthorized internal Assurance Case calls, cross-tenant attacks, rate limiting |
| RCA methods | Branching 5 Whys and editable Fishbone persisted across devices; FACT/HYPOTHESIS/conclusion/evidence constraints; multiple methods per CAR |
| Pareto | Tenant-bounded source sample, sorting and cumulative percentage, zero-data/bounded-volume handling, persisted reproducibility |
| Drafts/attachments | Debounced revisions, device recovery, optimistic 409 conflict, concurrent tabs, retries, crash/failure, failed upload, storage integrity |
| Quality lifecycle | Review independence, rework, evidence ownership, individual action owner/dates, effectiveness rejection, premature close/reopen blocked |
| UI/accessibility | Actual external and internal browser flows, keyboard, labels, focus, mobile/desktop, performance on large cases |
| Compatibility | Previously issued invites, pre-existing submitted CARs and evidence, control-loop owners, legacy register/report consumers |
| CI | Relevant Python, PostgreSQL, frontend/unit, Playwright, build, lint/typecheck and repository workflow checks all passed; skipped checks explained |

No test pass, production readiness, regulator compliance or vulnerability exploit is claimed at Phase 1. Trace gate outcomes and fixes in `CAR_RCA_IMPLEMENTATION_LEDGER.md`.

## 10. Unverified questions that must be answered from source and running tests

1. Exact deployment exposure and proxy/cache behavior of bearer invite tokens; need real API/access logs and middleware configuration.
2. Whether every invitation endpoint receives consistent per-request RLS context before tenant-scoped queries; need middleware/DB-session and PostgreSQL probe.
3. Whether provider account grants can safely substitute for public invite capability; need current provider/partner session code and IAM matrix.
4. Whether any existing task/action domain already supports per-CAR assigned actions; need task domain and reference indexes.
5. Whether live file storage is already remapped to shared object storage; need active storage adapter/deployment configuration.
6. Whether an Assurance Case can be atomically associated with one CAR without proliferating source truth; need explicit source reference validation and transaction code.
7. Whether newest CI failures/PR review comments are attributable to this work; need current workflow runs rather than infer from static files.
8. Whether actual close/reopen independence and archival requirements match the *approved* AMO manuals and applicable regulatory procedures; no regulatory certification inferred.

### Source links (baseline SHA)

- [CAR base models](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/backend/amodb/apps/quality/models.py)
- [CAR router](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/backend/amodb/apps/quality/router.py)
- [Public route replacement](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/backend/amodb/apps/quality/public_invite_extensions.py)
- [Assurance Case source](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/backend/amodb/apps/quality/assurance_case_router.py)
- [Control loop](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/backend/amodb/apps/quality/car_control_loop.py)
- [Public invitation UI](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/frontend/src/pages/PublicCarInvitePage.tsx)
- [Draft implementation](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/frontend/src/services/qmsCarInviteDraft.ts)
- [Internal RCA analysis](https://github.com/periljames/amo-portal/blob/75ab74c34422732f175d17cdae2acdb1879a1146/frontend/src/pages/qms/analysis/AnalysisInvestigation.tsx)
