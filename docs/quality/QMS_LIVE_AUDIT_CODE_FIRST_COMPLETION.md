# QMS Live Audit — Code-First Completion Freeze

**PR:** #502  
**Lifecycle:** `SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE`  
**State:** implementation-complete against the supplied Live Audit operating specification; validation intentionally deferred.

This document is the authoritative implementation checkpoint for the current PR branch. It records what is present in source code. It does **not** claim that the current head is CI-green, migration-proven, browser-proven, merge-ready, or production-ready.

## Architectural rule

There is one audit occurrence and one authoritative workflow. The branch reuses the existing Audit Programme, People & Privileges, checklist, finding, CAR/CAPA, report-governance and archive domains. It does not introduce a parallel audit state machine.

Canonical audit URLs are the six-stage occurrence routes. On those routes the legacy Audit Run Hub cockpit no longer mounts, preventing duplicate controls and duplicate data queries. Legacy audit URLs remain available as compatibility surfaces until validation is complete.

## 1. Setup

The canonical Setup workspace owns:

- audit title, scope and criteria;
- auditee identity/contact;
- planned dates;
- notification preferences and reminder interval;
- governed internal auditor assignments;
- opening and closing meeting records;
- governed audit notice lifecycle.

Auditor assignment is separated from the general audit PATCH. The assignment endpoint reuses the existing People & Privileges hard gates for:

- active workforce identity;
- active Quality privilege;
- authorised privilege scope;
- current required training;
- concurrent-assignment capacity;
- audit-specific independence declaration.

The same person cannot occupy multiple auditor roles on one occurrence. Setup displays failed gates before commit and the server re-evaluates them during assignment.

## 2. Prepare / Pre-Audit Room

Preparation uses governed document-request records with:

- request type;
- linked audit criterion;
- required/optional status;
- due date;
- upload, controlled-DMS, or upload-or-controlled source mode;
- optional exact controlled document and revision selection;
- accepted, rejected/returned and waived review states.

Auditee document responses support both governed upload and controlled-DMS linking. The public workspace never enumerates the tenant document library. A controlled link is accepted only when the selected document/revision belongs to the same tenant and revision/document relationship.

Internal review shows both uploaded file evidence and the auditee's actual controlled-record response.

External participation supports:

- auditee guest via purpose-bound `EMAIL_LINK`;
- external auditor via `EMAIL_LINK` or implemented `PASSKEY` assurance;
- scoped participant permissions and expiry/revocation.

Unimplemented generic `MFA` is not selectable in the UI and is rejected by the backend if an older/API client attempts to request it.

## 3. Live

The canonical Live workspace provides one fieldwork surface with:

- frozen checklist execution;
- versioned/idempotent checklist mutations;
- base-version conflict rejection;
- attributable auditor notes;
- governed evidence artifacts;
- atomic non-conformity/observation creation;
- realtime occurrence collaboration/presence;
- internal encrypted offline queue/replay;
- external-auditor encrypted offline structured mutation queue/replay;
- explicit conflict handling rather than silent last-write-wins.

Each checklist question projects its source context directly from the frozen checklist binding:

- checklist reference;
- requirement reference;
- regulatory source;
- manual source;
- exact template code/revision;
- checklist content SHA-256;
- expected evidence;
- mandatory/optional status;
- governed finding trigger.

This projection uses the existing immutable binding snapshot and does not issue an N+1 request per checklist item.

Realtime refresh is occurrence-scoped. Events for other audits are ignored; replay-window reset refreshes the active Quality occurrence rather than every active application query.

## 4. Auditee collaboration

The purpose-bound auditee workspace exposes only server-filtered data authorised for that audit participant, including:

- audit scope/criteria/dates;
- opening, closing and follow-up meetings;
- governed preparation requests;
- controlled-DMS or file responses;
- fieldwork progress when granted;
- explicitly released findings;
- explicitly released governed evidence;
- CARs whose linked findings are currently released;
- closing narrative;
- closing-draft response;
- issued-report download and receipt acknowledgement.

Private auditor notes, unreleased findings/evidence and unrelated tenant data are not projected to the public workspace.

The auditee records are deliberately distinct:

1. released-finding receipt;
2. closing-meeting response against the exact draft revision/hash;
3. issued-report receipt against the exact issued revision/hash.

A closing response is not a waiver or automatic acceptance of findings.

## 5. Closing

The Closing workspace uses persisted authoritative records for:

- management summary;
- audit conclusion;
- positive-practices statement;
- closing-meeting status;
- finding/CAR release;
- deterministic report generation;
- governed report revision adoption;
- auditee closing response;
- internal review and approval;
- WebAuthn/passkey signing;
- immutable issue;
- execution closure;
- policy-controlled assurance output;
- public verification token creation.

The generated report snapshot is `QMS_AUDIT_REPORT_SNAPSHOT_V2` and includes the saved closing narrative and occurrence meetings. Report generation is blocked until:

- fieldwork has an actual end;
- no checklist row remains `NOT_VERIFIED`;
- management summary is saved;
- conclusion is saved;
- a positive-practices statement is saved, including an explicit statement when none were observed.

The report lifecycle remains:

`DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED → SUPERSEDED`

Issue is server-gated to a valid WebAuthn signature for the exact current approved report revision/SHA-256. Password re-authentication is not treated as equivalent approval evidence in the canonical closing flow.

## 6. Finding / CAR sharing at closing

Official non-conformity creation continues to use the canonical finding/CAR transaction. Closing does not create a duplicate CAR engine.

Quality explicitly releases a finding to the auditee. The public collaboration projection returns a linked CAR only when the linked finding's latest release state is `RELEASED`. This creates one release boundary for finding/CAR visibility.

## 7. Follow-up

The dedicated Follow-up workspace uses:

- one audit-filtered CAR register query;
- one detailed CAR control-loop query for the selected CAR only;
- open/overdue/escalated metrics;
- next required action;
- milestone progress;
- deadline-extension decisions;
- closure blockers;
- authoritative follow-up readiness;
- explicit complete/reopen lifecycle actions.

Detailed RCA/CAPA review, evidence, extension risk, reminders, escalation and effectiveness remain in the existing governed CAR control loop rather than being duplicated on the audit page.

Execution closure and follow-up completion remain separate.

## 8. Archive

Archive continues to use governed retention policy, immutable manifest/package hashes, legal holds, disposition review and append-only disposition evidence. Follow-up completion remains an independent prerequisite according to archive policy.

## 9. Evidence and public verification

Governed audit evidence is an immutable artifact with tenant/audit/checklist/finding linkage, private storage reference, filename/content type/size/SHA-256 metadata and attributable actor. Auditee evidence release refers to artifact IDs, not raw storage paths.

Public report verification uses a high-entropy token whose raw value is not persisted. Verification can expose the exact issued report revision/SHA and signing/assurance metadata without exposing the controlled document itself. Local file SHA comparison is supported in the browser.

## 10. Mobile

The mobile `Report & closeout` control is mounted for audit occurrences, recognises both canonical `/closing` and legacy `?tab=closeout|report`, persists through refresh because it is derived from the URL, and focuses the actual closing workspace. It is rendered only at the mobile breakpoint.

## Code-completion freeze rule

From this checkpoint forward, PR #502 should enter a **validation-only** phase unless testing proves a source defect. Do not perform opportunistic workflow rewrites while validating.

Validation still required before any merge-readiness claim:

1. Python import/syntax validation for new routers/models.
2. Frontend typecheck/build.
3. Clean Alembic `upgrade heads` and migration-chain verification.
4. Targeted backend contracts for WebAuthn, closing gates, evidence, external PASSKEY, public verification, external offline replay and presence.
5. Targeted browser tests for two-party collaboration, mobile closeout refresh, programme transition persistence, governed DMS preparation and same-day closing.
6. Exact-head full repository-required CI only after targeted validation is green.
7. Compare/sync with current `main`, mergeability check and unresolved-review sweep.

No statement in this document is a claim that those validation steps have already passed on the current head.
