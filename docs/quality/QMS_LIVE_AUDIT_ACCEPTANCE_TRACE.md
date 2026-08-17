# QMS Live Audit Acceptance Trace

This matrix tracks the supplied Live Audit operating specification against PR #502 after the code-completion pass.

**Important:** `IMPLEMENTED` means the material source code exists on the branch. It does **not** mean the current head has passed migrations, build, browser tests or full CI. Validation is intentionally deferred until the code-first freeze is complete.

| # | Requirement | Code status | Current implementation |
|---|---|---|---|
| 1 | Programme occurrence becomes an audit | EXISTING | Existing Programme / Planner / audit occurrence |
| 2 | Schedule audit | EXISTING | Governed planner and schedule lifecycle |
| 3 | Assign internal lead/audit team | IMPLEMENTED | Canonical Setup + People & Privileges hard-gated occurrence assignment |
| 4 | External auditor invitation | IMPLEMENTED | Purpose-bound participant/grant model; EMAIL_LINK or PASSKEY |
| 5 | Independence/eligibility blocks assignment | IMPLEMENTED | Active privilege, scope, training, capacity and audit-specific independence gates |
| 6 | Notice issue / acknowledgement | IMPLEMENTED | Governed notice lifecycle in Setup |
| 7 | Explicit opening/closing meetings | IMPLEMENTED | Occurrence meeting records in Setup, Closing and public projection |
| 8 | Auditee document requests | IMPLEMENTED | Governed request metadata with type, criterion, required flag and due date |
| 9 | Upload or controlled-DMS response | IMPLEMENTED | Secure upload plus tenant/revision-validated DMS link |
| 10 | Auditor accept / return / waive | IMPLEMENTED | Governed request review states |
| 11 | Exact checklist revision bound | EXISTING / PROJECTED | Frozen binding revision and SHA reused by Prepare/Live |
| 12 | Source/expected evidence shown in Live | IMPLEMENTED | Immutable binding snapshot projected per checklist item without N+1 calls |
| 13 | Live checklist response persists | IMPLEMENTED | Versioned/idempotent fieldwork mutation |
| 14 | Realtime collaboration | IMPLEMENTED | Occurrence-scoped event stream + presence; exact-head browser proof deferred |
| 15 | Internal offline queue/replay | IMPLEMENTED | Encrypted portal outbox + idempotency/base-version contracts |
| 16 | External auditor offline queue/replay | IMPLEMENTED | Guest-specific encrypted structured outbox; fresh session/CSRF on replay |
| 17 | Stale conflict visible | IMPLEMENTED | Server base-version rejection; no silent last-write-wins |
| 18 | Governed evidence artifacts | IMPLEMENTED | Immutable tenant/audit/checklist/finding artifacts with SHA-256 and private storage refs |
| 19 | Auditee sees released data only | IMPLEMENTED | Server-filtered finding/evidence projection |
| 20 | Finding receipt separate from acceptance | IMPLEMENTED | Purpose-bound finding acknowledgement |
| 21 | Official NC creates canonical CAR | EXISTING / REUSED | Existing atomic finding/CAR workflow; no duplicate CAR engine |
| 22 | Closing finding/CAR sharing | IMPLEMENTED | Finding release boundary; CAR projected only for currently released findings |
| 23 | Closing narrative persisted | IMPLEMENTED | Management summary, conclusion, positive-practices statement |
| 24 | Fieldwork freeze before report | IMPLEMENTED | Actual-end and NOT_VERIFIED generation gates |
| 25 | Report generated without manual upload | IMPLEMENTED | Deterministic report snapshot/PDF artifact |
| 26 | Report includes closing narrative/meetings | IMPLEMENTED | Snapshot/report schema V2 |
| 27 | Generated artifact adopted into governed report | IMPLEMENTED | Generated artifact → governed DRAFT revision |
| 28 | Auditee closing response before review/approval | IMPLEMENTED | Exact draft revision/SHA acknowledgement/comment/decline record |
| 29 | Quality review / approval | EXISTING / REUSED | Existing report lifecycle remains authoritative |
| 30 | WebAuthn/passkey electronic signing | IMPLEMENTED | Exact APPROVED revision/SHA, signer, reason, ceremony evidence |
| 31 | Issue refuses stale/missing signature | IMPLEMENTED | Server-side ISSUE gate for current passkey evidence |
| 32 | Issued report immutable | EXISTING / STRENGTHENED | Governed revision + SHA lineage |
| 33 | Public verification | IMPLEMENTED | Hashed high-entropy verification token and local SHA comparison |
| 34 | Policy-controlled certificate/approval output | IMPLEMENTED | NONE / REPORT_ONLY / APPROVAL_LETTER / CERTIFICATE / ATTESTATION |
| 35 | Auditee issued-report receipt | IMPLEMENTED | Exact issued revision/SHA receipt record |
| 36 | Execution closes while CAR remains open | EXISTING / REUSED | Execution and follow-up are independent |
| 37 | RCA / CAP submission | EXISTING | Existing CAR external response workflow |
| 38 | Quality reject / return / accept | EXISTING | Existing CAR control loop |
| 39 | Reminders / escalation | EXISTING | Existing CAR reminder/escalation service |
| 40 | Extension with risk / decision | EXISTING | Existing controlled CAR deadline-change workflow |
| 41 | Effectiveness and final closure | EXISTING | Existing CAR/effectiveness workflow |
| 42 | Dedicated Follow-up workspace | IMPLEMENTED | Audit-filtered CAR queue + selected control-loop detail + readiness gate |
| 43 | Archive governance | IMPLEMENTED / REUSED | Retention policy, manifest/package hashes, legal hold and disposition |
| 44 | Cross-tenant public/direct-object isolation | IMPLEMENTED IN SOURCE | Tenant RLS/scoped grants/object checks; adversarial validation deferred |
| 45 | Mobile closeout deep link | IMPLEMENTED | URL-derived mobile control for canonical Closing and legacy closeout/report links |
| 46 | Unimplemented MFA not presented | IMPLEMENTED | UI omits MFA; backend rejects MFA creation fail-closed |
| 47 | Competing legacy occurrence surface removed | IMPLEMENTED | Canonical stage URLs use lightweight route shell; legacy Run Hub does not mount |
| 48 | Narrow realtime/query invalidation | IMPLEMENTED | Active occurrence only; other audit events ignored; reset no longer refetches whole app |

## Current implementation map

### Canonical occurrence

- `AuditSetupWorkspace.tsx`
- `AuditPrepareWorkspace.tsx`
- `LiveAuditWorkspace.tsx`
- `AuditClosingNarrativePanel.tsx`
- `AuditClosingWorkspace.tsx`
- `AuditFollowUpWorkspace.tsx`
- `AuditArchiveWorkspace.tsx`
- `AuditLifecycleRail.tsx`
- `QualityAuditOccurrenceStageShell.tsx`

### Preparation / external collaboration

- `audit_occurrence_completion_router.py`
- `audit_controlled_document_collaboration_router.py`
- `audit_external_participant_guard_router.py`
- `audit_external_passkey_router.py`
- `PublicAuditAccessPage.tsx`
- `AuditDocumentSubmissionReviewPanel.tsx`

### Live / evidence / realtime

- `audit_checklist_execution_*`
- `audit_evidence_*`
- `audit_presence_*`
- `qmsExternalAuditOutbox.ts`
- `QualityDataFreshnessCoordinator.tsx`

### Closing / verification

- `audit_report_composition.py`
- `audit_live_completion_router.py`
- WebAuthn credential/challenge models and migration
- public verification token model/router/page

## Release rule

The source implementation is frozen for validation. No `IMPLEMENTED` row is a merge-readiness claim. The next phase must prove the exact current head with targeted import/type/build/migration/backend/browser checks before full repository CI and review reconciliation.
