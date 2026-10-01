# QMS Auditor/Auditee Workflow — Implementation Report

PR: #554  
Branch: `codex/auditor-workflow-foundation-20260930`  
Basis: 30 Sep 2026 Auditor Workflow Full-Stack Implementation Mandate + supplied audit-workflow assessment.

> This report distinguishes implemented source-code behavior from deployed-environment verification. Production topology, cross-pod runtime behavior and real-device offline interruption behavior are not claimed unless separately proven.

## A. Codebase findings

### Confirmed architecture

| Area | Confirmed implementation | Evidence |
|---|---|---|
| Frontend | React + TypeScript + Vite SPA | `frontend/package.json` |
| Frontend data/state | TanStack Query, existing service abstractions, route-driven QMS occurrence workspaces | `frontend/package.json`, `frontend/src/components/QMS/QualityEnhancementsHost.tsx` |
| Backend | FastAPI + SQLAlchemy | `backend/amodb/main.py`, `backend/amodb/apps/quality/*_router.py` |
| Database | PostgreSQL-targeted SQLAlchemy models with Alembic migrations and tenant RLS contracts | `backend/amodb/database.py`, `backend/amodb/alembic` |
| Authentication/RBAC | JWT/internal identity plus tenant-scoped Quality permissions; purpose-bound external audit grants | `backend/amodb/security.py`, Quality tenant-security/external-access routers |
| Audit lifecycle | Setup → Prepare → Live → Closing → Follow-up → Archive | `frontend/src/features/qms/auditSession/auditSessionRoutes.ts`, `backend/amodb/apps/quality/audit_session_router.py` |
| Checklist governance | Versioned template revisions, content hashes, audit binding snapshots | `audit_checklist_template_models.py`, `audit_checklist_template_router.py` |
| Fieldwork concurrency | Entity version, client mutation ID, device sequence, base version, append-only mutation receipt | `audit_checklist_execution_models.py`, `audit_checklist_execution_router.py` |
| Realtime | Shared frontend realtime provider/SSE; canonical DB audit events | `backend/amodb/apps/events/router.py`, existing realtime frontend provider |
| Offline | Encrypted tenant/user-scoped IndexedDB outbox; deliberate downloaded audit work package; separate durable evidence queue | `qmsAuditOfflinePack.ts`, `qmsOfflineAuditEvidence.ts`, `offlinePersistence.ts` |
| Reporting | Structured-data report composition, governed report revisions, approval/signature/issue | `audit_report_composition.py`, closing/report governance routers |
| CAPA/follow-up | Existing CAR/CAPA control loop retained | `AuditFollowUpWorkspace.tsx`, existing CAR services/routes |
| Design system | Existing semantic tokens and QMS component/CSS conventions | `frontend/src/styles/tokens.css` |

No duplicate audit, CAPA, report, network, state-management or design-system subsystem was introduced.

## B. Blockers rectified

### B1. Mutable execution state invalidated issued preparation
**Problem:** preparation fingerprint included mutable document request status/file/review timestamps.  
**Consequence:** valid auditee submissions/reviews after preparation issue could falsely stale preparation and block fieldwork.  
**Remediation:** preparation definition hash now excludes mutable execution fields while preserving request definitions and governed source identity.  
**Files:** `audit_preparation_router.py`.

### B2. Readiness treated every required request as the same gate
**Problem:** no distinction between pre-issue, pre-fieldwork, during-fieldwork and non-blocking requests.  
**Remediation:** governed `requirement_stage` added and enforced server-side.  
**Files:** migration, occurrence completion models/router, preparation router, Prepare UI.

### B3. Source response vocabulary could be lost
**Problem:** canonical workflow outcomes were insufficient to preserve source checklist semantics such as YES/NO/N/A or other explicitly governed values.  
**Remediation:** source `response_value` is stored separately from canonical status; response schemes are frozen with template revisions/bindings. Ambiguous values such as U/S require explicit source mapping and are never inferred.  
**Files:** migration, response policy, checklist template router, execution models/router, fieldwork UIs/services.

### B4. Competing checklist write semantics
**Problem:** legacy/direct checklist write path coexisted with guarded versioned/idempotent fieldwork mutation semantics.  
**Remediation:** authoritative fieldwork writes use the guarded command semantics with lifecycle, base-version, idempotency and permission checks.

### B5. Offline evidence was not durable fieldwork evidence
**Problem:** ordinary upload paths were live-only.  
**Remediation:** internal and external field evidence can be encrypted locally with SHA-256, mutation identity, captured base version and explicit upload/conflict/error state until server acknowledgement.  
**Files:** `qmsOfflineAuditEvidence.ts`, `qmsExternalOfflineEvidence.ts`, Live/External fieldwork components.

### B6. Offline restart depended on incidental API cache
**Problem:** live-authority queries are deliberately excluded from persisted generic QMS cache, so a stored audit pack alone did not reconstruct Live Audit after restart.  
**Remediation:** the deliberate work package now carries a frozen fieldwork-authority state and projects occurrence, session, checklist binding and checklist execution state when disconnected.  
**Files:** `audit_preparation_router.py`, `qmsAuditOfflinePack.ts`, `qmsAuditOccurrenceResolver.ts`, `qmsAuditSession.ts`, `qmsChecklistTemplates.ts`, `qmsChecklistExecutionGovernance.ts`.

### B7. Process-local realtime broker could miss committed changes
**Problem:** DB commit and broker publication were not atomic and process-local broker history could not provide cross-process durability.  
**Remediation:** SSE retains low-latency in-process delivery but also sweeps committed canonical audit events from the database using short-lived sessions and durable cursors, recovering commit-before-publish and process-boundary gaps.  
**Files:** `backend/amodb/apps/events/router.py`.

### B8. Generated reports depended on local cache storage
**Problem:** local filesystem alone is not a sufficient production guarantee for issued audit artifacts.  
**Remediation:** atomic local writes plus existing AeroDoc S3/Azure/on-prem replication/restore are used; production generation fails closed when no durable replication target is configured; restored artifacts are SHA-256 verified.  
**Files:** report composition/adoption routers, `storage_replication.py`.

### B9. Audit trail existed but was not an obvious occurrence workspace
**Remediation:** tenant-scoped Activity API and visible Activity functional navigation expose canonical audit events plus preparation events with actor/time/action/target/reason.  
**Files:** `audit_preparation_router.py`, `qmsAuditGovernance.ts`, `AuditPrepareWorkspace.tsx`, `auditSessionRoutes.ts`.

## C. Database changes

Migration: `quality_20260930_auditor_workflow_foundation.py`.

Material additions/extensions include:
- document request `requirement_stage`;
- checklist execution `response_value`;
- participant execution `response_value`;
- first-class immutable Audit Work Package storage/lineage on the branch;
- associated constraints/RLS/immutability controls following existing migration conventions.

Historical audit/checklist records are not replaced by mutable current templates.

## D. Backend changes

### Preparation/work package
- deterministic readiness for issue and fieldwork;
- immutable work-package issue/supersession/hash;
- offline pack assembled from issued work package plus current permitted execution/findings/evidence metadata;
- fieldwork authority captured at download;
- audit Activity endpoint.

### Checklist
- governed template-driven response schemes;
- explicit source-to-canonical mapping;
- frozen item-definition rule enforcement;
- N/A justification, required notes and required evidence enforced server-side;
- entity-version conflict detection;
- idempotent mutation receipts.

### Evidence
- governed evidence remains linked to checklist/finding context;
- opaque artifact references rather than raw storage paths;
- SHA-256 retained;
- upload authorization and base-version checks remain server-side.

### Realtime
- canonical database audit events remain authoritative;
- durable DB sweep supplements the process-local low-latency broker;
- duplicate event delivery is suppressed per connection.

### Reporting
- report snapshot remains structured-data driven;
- source response value is retained in report source data;
- atomic artifact write;
- durable replication/restore and hash validation;
- governed report lifecycle remains DRAFT → review → approval → WebAuthn-bound issue.

### Authorization
Internal audit read/write remains tenant + Quality capability + assigned-team constrained. External participants use purpose-bound audit grants and scoped released-data projections. UI hiding is not used as the authority boundary.

## E. Frontend changes

### Prepare
- preparation intelligence/history;
- deterministic readiness/blockers;
- controlled references;
- DMS checklist search/binding;
- controlled response scheme selection;
- realtime checklist composer with source reference, evidence expectation, method, sampling, guidance, applicability rule, response rules and mandatory state;
- composer search, section navigation, incomplete/evidence/applicability filtering;
- governed document requests/stages;
- external participant invitations/scopes;
- deliberate offline-package download/removal/status;
- Activity/audit-trail surface.

### Live fieldwork
- focused one-question workflow;
- template-driven response buttons;
- requirement/reference/source/evidence context;
- search and filters for unanswered, findings/observations and evidence-required items;
- previous/next within filtered results;
- finding creation from checklist context;
- evidence capture;
- explicit ONLINE/OFFLINE/SYNCING/PENDING/SYNC ERROR/CONFLICT states;
- local-vs-server save language remains distinct.

### Auditee/external
- separate purpose-scoped audit access;
- document/evidence requests;
- released findings/evidence;
- assigned external-auditor checklist projection;
- source response scheme preserved;
- scoped guest/external permissions.

### Closing/follow-up/archive
Existing governed workspaces are reused:
- closing narrative, report composition/generation/adoption/review/approval/signing/issue;
- audit-filtered CAR/CAPA control loop and effectiveness/follow-up gates;
- retention/archive/legal-hold/disposition controls.

## F. Auditor journey

`Audit register/planner`
→ Setup audit definition/team/auditee/schedule
→ Prepare risk/history/source context
→ Select/create controlled checklist
→ Define request stages/evidence expectations/sampling/applicability
→ Resolve readiness blockers
→ Issue immutable preparation/work package
→ Make audit available offline
→ Live fieldwork
→ answer checklist / notes / evidence / finding
→ concurrent version/conflict control
→ complete fieldwork
→ Closing narrative
→ Generate deterministic report
→ Review / approve
→ WebAuthn sign exact approved revision/hash
→ Issue
→ CAR/CAPA follow-up
→ effectiveness/closure
→ Archive.

## G. Auditee journey

Purpose-bound invitation
→ audit summary/scope/dates/meetings
→ requested documents/evidence
→ upload or link permitted records
→ view only released findings/evidence
→ closing response/acknowledgement where permitted
→ issued report receipt when authorized
→ CAR/CAPA obligations/responses.

Auditee access does not expose internal auditor notes/drafts merely through frontend hiding.

## H. Offline trace

### Implemented source-code path
1. Auditor issues governed preparation.
2. `Make available offline` fetches the server-built pack.
3. Server freezes work package identity/SHA, execution baseline and fieldwork-authority state.
4. Browser encrypts the pack into tenant/user-scoped IndexedDB.
5. On disconnect/restart, occurrence resolution, session stage, checklist binding and execution can be reconstructed from that exact pack.
6. Checklist/finding mutations use the durable ordered outbox with original client mutation ID, device sequence and base version.
7. Binary evidence is stored separately as encrypted local evidence with SHA-256 and captured base version.
8. On reconnect, authority is revalidated by the server; stale writes return conflict rather than overwrite.
9. Successful server acknowledgement replaces pending local state; evidence local binary is removed only after accepted/hash-verified upload.

### Important declared limitation
Where a frozen checklist rule requires **server-linked evidence for a particular response**, the final authoritative response cannot truthfully be considered synchronized before the separately queued binary evidence has been accepted and linked. The UI retains pending state rather than pretending the evidence exists server-side. Real-device interruption/restart testing remains a release-hardening requirement.

## I. Realtime trace

Mutation
→ server permission/lifecycle/version validation
→ DB checklist/event transaction
→ commit
→ low-latency broker publish where available
→ SSE client delivery.

If broker publication is missed or the connected client is served by another process:
→ SSE durable sweep reads committed canonical audit events after its cursor
→ de-duplicates event IDs
→ delivers change
→ existing frontend invalidation refreshes the relevant audit projection.

The DB remains authoritative; presence/realtime transport is not the source of truth.

## J. Report trace

Persisted audit definition + meetings + closing narrative + checklist execution + findings + CARs + preparation requests
→ canonical report snapshot
→ source SHA-256
→ deterministic PDF rendering
→ atomic local cache artifact
→ durable configured replication
→ governed DRAFT adoption
→ internal review
→ approval
→ WebAuthn evidence bound to exact revision/artifact SHA
→ immutable ISSUE
→ controlled later revision rather than silent replacement.

## K. Responsive verification

Source-code responsive contracts exist for:
- Prepare: desktop + multiple tablet/mobile breakpoints;
- Live: desktop three-area focus layout, tablet collapse, mobile single-column fieldwork, reduced-motion handling;
- Closing/completion: tablet/mobile breakpoints;
- public/external audit access: responsive QMS public audit styles.

**Current source inspection confirms the responsive implementations. Real-device/browser-matrix acceptance on the final head must complete before production verification is claimed.**

## L. Verification performed / observed

### Previously green on this PR lineage
- Quality backend contract;
- Quality PostgreSQL schema/RLS;
- QMS Live Audit backend contract;
- QMS Live Audit PostgreSQL contract;
- QMS External Draft backend/PostgreSQL contracts;
- QMS Assurance backend/PostgreSQL contracts;
- Live Audit Security;
- clean PostgreSQL migration through Alembic heads.

### Added focused coverage
- `backend/amodb/apps/quality/tests/test_auditor_workflow_foundation.py` covers document-request stage gating and response-scheme semantics.
- `frontend/src/services/qmsAuditOfflinePack.test.ts` covers frozen binding, source response vocabulary, execution restoration and Live-stage projection from a downloaded work package.
- Offline pack test is included in `npm run test:qms-offline`.

### Current-head status
GitHub Actions for the current head are still queued/running at the time of this report. A pending check is not recorded as passed.

## M. Retained test/hardening backlog

Release hardening still must exercise:
- browser restart while fully offline;
- real tablet/field device encrypted storage;
- interrupted evidence upload/retry;
- multiple queued evidence files for the same checklist item;
- cross-pod/instance realtime with deliberate process termination after DB commit;
- replay beyond normal in-memory broker history;
- multi-device version conflict resolution;
- expired/revoked offline authority on reconnect;
- 500+ item checklist responsiveness;
- 100+ finding/CAR report generation;
- report reproducibility/golden datasets;
- PDF fidelity/signature/verification;
- complete auditor E2E;
- complete auditee E2E;
- accessibility/keyboard/screen-reader checks on the final head;
- production object-storage/backup topology.

This register is not a waiver for any obvious source-code/runtime defect found by current CI.

## N. Known limitations / not verified

- Production S3/Azure/SFTP/object-storage configuration is environment-specific and not provable from source.
- Production cross-pod deployment topology is not confirmed.
- Real-device offline binary restart/interruption behavior is not yet confirmed by a completed device acceptance run.
- An evidence-required authoritative answer remains pending until its required binary evidence is accepted/linked server-side; the implementation deliberately does not fake a synchronized result.
- Current-head CI is still running; release readiness is not claimed until required checks are reviewed.

## O. File manifest

### Database
- `backend/amodb/alembic/versions/quality_20260930_auditor_workflow_foundation.py`

### Backend — preparation/checklists/fieldwork/evidence
- `audit_preparation_models.py`
- `audit_preparation_router.py`
- `audit_checklist_response_policy.py`
- `audit_checklist_template_router.py`
- `audit_checklist_execution_models.py`
- `audit_checklist_execution_router.py`
- `audit_external_fieldwork_router.py`
- `audit_occurrence_completion_models.py`
- `audit_occurrence_completion_router.py`

### Backend — realtime/reporting/storage
- `backend/amodb/apps/events/router.py`
- `audit_report_composition.py`
- `audit_report_composition_router.py`
- `audit_generated_report_adoption_router.py`
- `storage_replication.py`

### Frontend — auditor/auditee workspaces
- `QualityChecklistTemplateHost.tsx`
- `AuditPrepareWorkspace.tsx`
- `LiveAuditWorkspace.tsx`
- `LiveAuditEvidenceStrip.tsx`
- `ExternalAuditorFieldworkWorkspace.tsx`
- `PublicAuditAccessPage.tsx`
- `auditSessionRoutes.ts`

### Frontend — services/offline/sync
- `qmsAuditGovernance.ts`
- `qmsAuditOccurrenceCompletion.ts`
- `qmsAuditOccurrenceResolver.ts`
- `qmsAuditSession.ts`
- `qmsChecklistTemplates.ts`
- `qmsChecklistExecutionGovernance.ts`
- `qmsAuditEvidence.ts`
- `qmsAuditExternalAccess.ts`
- `qmsAuditOfflinePack.ts`
- `qmsOfflineAuditEvidence.ts`
- `qmsExternalOfflineEvidence.ts`
- `qmsExternalAuditOutbox.ts`
- `qmsExternalAuditorMutations.ts`

### Frontend — styles
- `qms-audit-prepare-workspace.css`
- `qms-live-audit-workspace.css`
- `qms-live-audit-completion.css`

### Tests/configuration
- `backend/amodb/apps/quality/tests/test_auditor_workflow_foundation.py`
- `frontend/src/services/qmsAuditOfflinePack.test.ts`
- `frontend/package.json`

## Prompt reconciliation — 1 Oct final source pass

The attached implementation mandate was rechecked against the current branch after the initial foundation PR. The following source gaps found in that pass were corrected rather than deferred:

- canonical Setup now exposes and persists the existing audit `location` field;
- canonical occurrence projection now returns supporting auditor IDs, preserving the complete team;
- quick opening/closing meeting scheduling preserves agenda, auditee department and responsible auditor;
- checklist answer provenance is fully mapped in the ORM and API (`answered_by_user_id`, `answered_at`);
- sampled-record information is preserved even when an adverse response and finding are committed atomically;
- the Activity workspace now includes checklist execution events, evidence uploads, report events and finding-release events in addition to general/preparation events;
- governed evidence upload now persists and publishes an audit-scoped realtime event, with durable DB replay as the recovery path;
- governed internal fieldwork mutations require durable browser storage and fail closed instead of falling back to a volatile in-memory queue;
- existing stable checklist item/section identity, section hierarchy metadata, revision effective date, evidence request/device/state metadata and response applicability/provenance fields were re-verified in source rather than reimplemented.

At source level, no additional mandate capability is intentionally deferred as a placeholder. Remaining items are executable validation and environment/deployment proof listed below. A failing current-head check must still be investigated before this PR can be called complete.

## Definition-of-done posture

The branch now materially covers the mandate's required vertical slices using the existing QMS architecture. **It must remain Draft until current-head build/lint/backend/PostgreSQL/browser/security checks are reviewed.** No production-complete claim should be made from source inspection alone.
