# AMO Portal Enterprise QMS/DMS — Phase 3 Verification Report (OPEN)

**Evidence cut:** 2026-11-11. **Consolidation PR:** [#570](https://github.com/periljames/amo-portal/pull/570) (draft, must not merge).  
**Working branch:** `feat/enterprise-qms-dms-consolidation-20261111`  
**HEAD inspected when drafting this report:** `61125a9f5c7c501ec4436037e5408298eccc33c7` (newer commits invalidate prior CI acceptance).  
**Main at inspection:** `86a66d2d3630518a67ff3f02d5c9467cdcdfd90d`. Recheck both before release.

> **PRODUCTION READINESS: NO — NOT VERIFIED.** This is a factual interim Phase 3 evidence report, not a release certificate. Do not close the programme or make regulator/ISO compliance claims from source presence or historical passing jobs.

## What is in the PR (source inspection, not system acceptance)

- PR #569 Office source/rendition and optional Graph/SharePoint working-file bridge, original source identity and explicit import to DMS draft with no automatic approval/publication. Current changes serialize competing imports by tenant-linked SharePoint file.
- PR #557 company library with search, saved views/favorites, bounded discovery, four presentations and original mainline Structure/provider-evidence links retained. DMS reader remains based on the existing PDF.js architecture.
- PR #558 source-of-truth audit checklist pagination and direct committed binding confirmation, exact frozen lineage for all instantiated questions, including beyond 100 bindings.
- Governed Quality workflows: risks and opportunities with versioned tenant matrix, management-review attendance and independently verified actions, process objectives/performance, calibration quarantine/certification/out-of-tolerance with Inventory gating, external regulator/customer correspondence/commitments, source-based reporting, manual-to-Training impact linkage.
- Archived evidence size integrity guards selectively reconciled from PR #512 and theme/filter fixes from #534. Mainline CAR and audit engines are preserved; no duplicate CAR engine.
- See [Baseline](ENTERPRISE_CONSOLIDATION_BASELINE.md) and [Ledger](ENTERPRISE_IMPLEMENTATION_LEDGER.md) for full reconciliation and outstanding requirements.

## Exact historical CI findings and corrective source commits

| Gate / evidence | Historical result | Verified source correction | Current final-HEAD acceptance |
| --- | --- | --- | --- |
| Quality frontend/Operational UI on `a4cbec55` | FAILED TS parser: invalid Python docstring in `documentMicrosoft.ts`, unclosed JSX in equipment and external pages; [run 42992294970](https://github.com/periljames/amo-portal/actions/runs/42992294970) | Typescript header fixed and both JSX grids closed | **NOT VERIFIED** (latest build must run) |
| Quality backend contract and PG schema/RLS at `a4cbec55` | PASSED under [run 42992294970](https://github.com/periljames/amo-portal/actions/runs/42992294970) | New QMS routes, risk-policy and shared code added afterward | **NOT VERIFIED on final HEAD** |
| Document Control domain on `a4cbec55` | 422 passed, 1 failed for old literal discovery-view pattern; [run 42992294828](https://github.com/periljames/amo-portal/actions/runs/42992294828) | Test now requires all legacy allowed view values plus new permission-scoped `shared-with-me`; source validation preserved | **NOT VERIFIED** |
| DMS operating model on `7d2ce13` | FAILED old shell/presentation source literal assumptions; [run 42997185240](https://github.com/periljames/amo-portal/actions/runs/42997185240) | Contract now checks original governed nav plus additional reader destinations and four presentation modes, no assertion bypass | **NOT VERIFIED** |
| CAR real browser 41999293028 on earlier #564 branch | FAILED after revised submission: response-read expected 1 received 0; [run 41999293028](https://github.com/periljames/amo-portal/actions/runs/41999293028) | Canonical authenticated response read no longer hides committed latest submission merely because parent CAR moved from PENDING_VERIFICATION to IN_PROGRESS; focused tests added | **NOT VERIFIED on final HEAD** |
| QMS Live Audit Security on prior head | PASSED [run 42992294700](https://github.com/periljames/amo-portal/actions/runs/42992294700) | Subsequent commits alter shared source | **NOT VERIFIED on final HEAD** |

No local checkout, fresh/upgrade PostgreSQL migration execution, production recovery rehearsal, Microsoft Entra tenant credentials or Word-export comparison fixture was available in this GitHub connector-only environment. Historical GitHub Actions jobs have run, but the most recent HEAD jobs were pending when this evidence was written. Do not present test-source files as tests executed.

## Required acceptance evidence not yet provided

1. Reconcile actual `main` and PR HEAD, route uniqueness/precedence, PostgreSQL Alembic heads, fresh and upgrade migrations and rollback plan.
2. TypeScript lint/build, backend import tests, QMS/DMS unit, DB contract, multi-tenant row-level security, Playwright, audit and CAR real-browser workflows on **exact final HEAD**.
3. Reproduce/close CAR original real-browser failure (run 41999293028) with actual committed response and reviewer read, not mocks.
4. DMS publication/source checksum, reader/rendition pixel comparison, DOCX section layouts, mixed orientation, controllers' verification, retry and forbidden writes.
5. Entra consent/callback, Microsoft Graph token rotation/revocation, stale eTags, duplicate/concurrent import, interrupted Graph downloads and cross-tenant denial with approved real tenant credentials.
6. Two-tenant full QMS workflows: risk/residual decision, management review attendance and action verification, calibration and Inventory issue, provider procurement restrictions, employee assignment authorization, Training and external correspondence.
7. Load/performance, accessibility/keyboard/mobile, evidence retention, object storage quotas, disaster recovery and actual production restore.
8. Review all open Codex comments, CI workflows and file conflicts. Never disable tests or auto-merge.

## Operational release decision

**NO GO.** The draft branch includes extensive work but the evidence does not show complete migration, backend, frontend, role, two-tenant browser, infrastructure and final-code CI acceptance. External Graph production tenant and real DOCX visual comparators are **BLOCKED** pending credentials and fixtures. Keep PR #570 in draft; record precise latest run outcomes here before considering review readiness. Deployment, migration and rollback steps must be derived from proven database upgrade and object-storage snapshots, not guessed in this report.
