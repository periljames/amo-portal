# QMS Live Audit — Current Execution Checkpoint

PR #502 is at a **code-completion freeze** for the canonical audit occurrence:

`SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE`

The current branch is **not** being declared CI-green or merge-ready. Tests and repository CI were intentionally deferred while the implementation surface was completed and reconciled.

## What is complete in source

### Canonical occurrence routing

Canonical six-stage URLs no longer mount the legacy Audit Run Hub cockpit. A lightweight Quality route shell preserves the portal layout while `QualityEnhancementsHost` owns the stage workspace, lifecycle rail, realtime coordination and mobile closeout state. Legacy non-stage audit URLs remain compatibility surfaces.

### Setup

- audit scope, criteria, dates and auditee;
- notification/reminder preferences;
- governed opening and closing meeting records;
- governed audit notice lifecycle;
- internal auditor assignment through People & Privileges hard gates rather than a general audit PATCH.

Assignment hard gates cover active identity, Quality privilege, authorised scope, required training, workload capacity and audit-specific independence.

### Prepare

- governed document/record/manual/form/certificate/register request metadata;
- linked criterion and required/optional control;
- due date;
- upload / controlled-DMS / upload-or-controlled source modes;
- exact controlled document/revision selection;
- secure auditee file submission;
- auditee controlled-DMS linking without document-library enumeration;
- internal review of both binary uploads and controlled-record responses;
- accept / return / waive review states;
- auditee EMAIL_LINK access;
- external-auditor EMAIL_LINK or PASSKEY access;
- unimplemented generic MFA omitted from UI and rejected by the backend.

### Live

- frozen checklist execution;
- immutable source lineage projected beside each question;
- expected-evidence statement projected from the checklist binding;
- versioned/idempotent fieldwork writes;
- conflict rejection instead of silent last-write-wins;
- governed evidence artifacts;
- atomic official finding/CAR creation;
- explicit finding/evidence release boundary;
- internal encrypted offline replay;
- external-auditor encrypted offline replay;
- presence and occurrence-scoped realtime refresh.

Realtime events belonging to other audits are ignored. A realtime reset refreshes only the active occurrence rather than all active application queries.

### Auditee collaboration

The purpose-bound external workspace can receive:

- scope/criteria/dates;
- occurrence meetings;
- preparation requests;
- controlled-DMS/file responses;
- permitted progress/presence;
- released findings and released evidence;
- CARs linked to currently released findings;
- closing narrative;
- exact-draft closing response;
- exact-issued-report download and receipt acknowledgement.

The server projection excludes private auditor notes, unreleased findings/evidence and unrelated tenant data.

### Closing

- persisted management summary, conclusion and positive-practices statement;
- explicit closing-meeting lifecycle;
- finding/CAR release action;
- deterministic `QMS_AUDIT_REPORT_SNAPSHOT_V2` composition;
- generated PDF source/artifact SHA-256;
- generated artifact adoption into governed report DRAFT;
- auditee closing response against exact draft revision/hash;
- internal review and approval;
- WebAuthn/passkey approval against exact APPROVED revision/hash;
- server-gated immutable ISSUE;
- independent execution closure;
- policy-controlled assurance artifact;
- public verification token and local SHA comparison.

Report generation fails closed until fieldwork is ended, no checklist row remains `NOT_VERIFIED`, and all three closing narrative statements are saved.

### Follow-up

The dedicated Follow-up workspace uses one audit-filtered CAR register query and only one detailed CAR control-loop query for the selected CAR. It exposes health, risk, next action, milestones, deadline decisions and closure blockers, while the existing CAR domain continues to own RCA/CAPA review, extensions, escalation, reminders, evidence and effectiveness.

### Archive

The existing governed retention/archive domain remains authoritative for policy revision, immutable manifest/package hashes, legal hold and controlled disposition.

## Code-completion defects corrected in the final pass

- removed the canonical route's competing legacy occurrence cockpit and its duplicate queries;
- removed auditor IDs from the general Setup PATCH and mounted the People-gated assignment flow;
- mounted the occurrence assignment backend router;
- corrected assignment/frontend contract drift;
- removed assumptions that `QMSAudit` has `updated_at`/`updated_by_user_id` fields;
- finished controlled-DMS reviewer visibility;
- retained checklist source/expected-evidence projection without N+1 requests;
- narrowed realtime invalidation to the active occurrence;
- verified server-filtered auditee meeting/CAR projection;
- verified closing report V2 consumes persisted narrative/meeting records;
- verified mobile closeout is URL-derived and mounted;
- verified MFA is non-selectable and fail-closed.

## Validation deliberately deferred

The current head still requires a validation-only phase. The next phase should not rewrite the workflow unless a test proves a source defect.

Recommended order:

1. Python import/syntax checks for new routers/models.
2. Frontend typecheck/build.
3. Clean Alembic `upgrade heads`.
4. Targeted backend contracts for assignment gates, governed DMS requests, WebAuthn, closing issue gates, evidence, external PASSKEY/offline replay, public verification and presence.
5. Targeted browser flows for canonical routing, auditee collaboration, two-party realtime, mobile closeout refresh and same-day closing.
6. Fix only proven failures.
7. Run full exact-head repository-required CI.
8. Recheck current-main divergence, mergeability and unresolved review threads.

No older CI result should be represented as proof for the current code-completion head.
