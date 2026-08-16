# QMS Live Audit Architecture

**Branch:** `agent/qms-live-audit-operating-workspace`  
**Implementation contract:** `deep-research-report.md` supplied for this work  
**Status:** Incremental implementation; this document distinguishes implemented from pending scope.

## Objective

Preserve the governed Quality domain introduced by merged PRs #488 and #499 while compressing the operator journey around one audit occurrence:

`SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE`

The occurrence experience is an orchestration layer. It does not replace the authoritative Audit Programme, Planner, preparation revision, notice, checklist, finding, report revision, CAR/CAPA, effectiveness, closeout or archive engines.

## Current route model

The existing audit route remains the compatibility owner and accepts occurrence-stage tails:

```text
/maintenance/:amoCode/quality/audits/:auditRef/setup
/maintenance/:amoCode/quality/audits/:auditRef/prepare
/maintenance/:amoCode/quality/audits/:auditRef/live
/maintenance/:amoCode/quality/audits/:auditRef/closing
/maintenance/:amoCode/quality/audits/:auditRef/follow-up
/maintenance/:amoCode/quality/audits/:auditRef/archive
```

Public purpose-bound access:

```text
/qms/audit-access/:token     one-time invitation exchange
/qms/audit-access            HTTP-only guest session workspace
```

The six-stage lifecycle rail is derived from the existing authoritative seven-stage workflow facts. Visiting a page never changes lifecycle completion.

## Implemented frontend workspaces

### PREPARE

`AuditPrepareWorkspace.tsx`

Uses existing governed data for:

- scope and criteria;
- preparation revision state;
- checklist bindings;
- prior audit history and CAR exposure;
- existing `QualityAuditDocumentRequest` records;
- Quality acceptance/return decisions;
- first-class external auditee/external-auditor participants;
- bounded participant permissions, expiry and revocation.

`AuditDocumentSubmissionReviewPanel.tsx` exposes controlled guest submissions to authorised Quality users without exposing private storage locators.

### LIVE

`LiveAuditWorkspace.tsx`

Uses the existing governed checklist execution engine. The response vocabulary remains:

```text
COMPLIANT
NONCOMPLIANT
OBSERVATION
NOT_APPLICABLE
NOT_VERIFIED
```

The page keeps checklist response, notes, evidence references and inline finding creation in one fieldwork surface.

`LiveFindingReleasePanel.tsx` adds an explicit disclosure boundary. A finding is not externally visible merely because it exists. Append-only `RELEASED` / `WITHDRAWN` events control auditee visibility.

### CLOSING

`AuditClosingWorkspace.tsx`

Uses the new report-composition service to build a deterministic PDF from a frozen canonical snapshot. Generation is blocked until:

- fieldwork has an `actual_end`; and
- no governed checklist execution row remains `NOT_VERIFIED`.

Generated artifacts record:

- source snapshot SHA-256;
- PDF SHA-256;
- template version;
- renderer version;
- actor/time;
- private storage reference.

Generation does **not** equal formal issue. Existing report revision governance remains authoritative for review, approval, issue and supersession.

## External participant model

New tenant-owned models:

```text
quality_external_identities
quality_audit_participants
quality_audit_access_grants
quality_audit_access_events
quality_audit_finding_release_events
quality_audit_document_submissions
```

External participants are not represented as fake tenant employees.

Invitation tokens are:

- high entropy;
- audit/grant/tenant bound;
- signed before tenant context is trusted;
- expiring;
- revocable;
- stored as SHA-256 hashes only.

The raw token is exchanged once for an HTTP-only strict-SameSite guest session and then removed from the browser URL.

## External released-data projection

The public browser never receives the internal audit object. The backend constructs an explicit projection containing only granted fields such as:

- audit identity/scope/criteria;
- optional progress;
- document requests;
- explicitly released findings/evidence;
- finding acknowledgement state;
- issued-report availability.

Private auditor notes, unreleased findings, internal assurance intelligence, competence/privilege data and unrelated records are not serialized to the external client.

## Document exchange

Guest submissions are stored as append-only evidence records with:

- safe filename;
- content type;
- byte size;
- SHA-256;
- participant;
- response comment;
- private storage locator;
- creation time.

The legacy request `file_ref` receives an opaque `audit-submission:<id>` reference rather than the filesystem path.

## Database controls

New tenant-owned tables use PostgreSQL RLS and `FORCE ROW LEVEL SECURITY` following current Quality patterns. Append-only history applies to external access events, finding release events, document submissions and generated report artifacts.

## Implemented migrations

```text
quality_260816_external_access
quality_260816_guest_documents
quality_260816_report_composition
```

The exact Alembic head topology remains subject to CI verification on the current PR head.

## Deliberately not duplicated

The branch does not create new engines for:

- audit programme/risk planning;
- planner scheduling/conflicts;
- notice governance;
- checklist template governance;
- checklist execution semantics;
- finding/CAR association;
- CAR/CAPA milestones/deadline/escalation;
- effectiveness;
- formal report revision transitions;
- execution-close/follow-up separation.

## Current incomplete architecture slices

1. QMS-specific use of the existing portal realtime publisher is not yet wired.
2. Controlled offline mutation idempotency/conflict semantics are not yet implemented.
3. Generated report artifact adoption into the existing governed report revision lifecycle is not yet implemented.
4. Electronic signature/passkey evidence is not yet ported from historical PR #280.
5. Audit-type artifact policy (`NONE`, `REPORT_ONLY`, `APPROVAL_LETTER`, `CERTIFICATE`, `ATTESTATION`) is not yet implemented.
6. Retention/legal-hold/disposition policy is not yet implemented.
7. Follow-up/archive occurrence pages still rely on existing specialist surfaces rather than final compressed workspaces.
