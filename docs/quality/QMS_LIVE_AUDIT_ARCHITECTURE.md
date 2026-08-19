# QMS Live Audit Architecture

**Branch:** `agent/qms-live-audit-operating-workspace`  
**Implementation contract:** uploaded QMS Frontend Deep Research and Fullstack Execution Specification  
**Architecture rule:** orchestrate the governed QMS domain; do not create parallel audit, finding, report, CAR/CAPA or closeout engines.

## Occurrence model

One audit occurrence is presented through:

`SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE`

The rail is a projection of authoritative backend state. Visiting a route never changes lifecycle completion.

Internal occurrence routes remain additive under the existing Quality route model:

```text
/maintenance/:amoCode/quality/audits/:auditRef/setup
/maintenance/:amoCode/quality/audits/:auditRef/prepare
/maintenance/:amoCode/quality/audits/:auditRef/live
/maintenance/:amoCode/quality/audits/:auditRef/closing
/maintenance/:amoCode/quality/audits/:auditRef/follow-up
/maintenance/:amoCode/quality/audits/:auditRef/archive
```

Purpose-bound external access uses:

```text
/qms/audit-access/:token     one-time signed invitation exchange
/qms/audit-access            HTTP-only scoped guest session
/qms/car-access/:token       governed CAR external response path
```

Vite development and production-preview middleware explicitly preserve these signed HTML deep links as SPA routes while JSON/API requests remain proxied.

## Prepare architecture

`AuditPrepareWorkspace.tsx` composes existing governed preparation data with:

- scope and criteria;
- preparation revision state;
- checklist bindings;
- prior audit/CAR exposure;
- document requests and controlled guest submissions;
- Quality acceptance/return decisions;
- first-class auditee/external-auditor participants;
- bounded permissions, expiry and revocation.

External participants are not fake tenant employees. Their identity/grant/session data is tenant-owned and protected by PostgreSQL RLS/FORCE RLS.

EMAIL_LINK is the implemented assurance mode. MFA/PASSKEY labels fail closed until a real ceremony exists.

## Live architecture

`LiveAuditWorkspace.tsx` reuses the canonical checklist execution vocabulary:

```text
COMPLIANT
NONCOMPLIANT
OBSERVATION
NOT_APPLICABLE
NOT_VERIFIED
```

Internal fieldwork mutations include client mutation ID, device ID/sequence, client timestamp and base version. The server records idempotent mutation receipts and rejects stale versions instead of applying last-write-wins.

### Realtime

Committed Quality audit events are published through the existing realtime broker only after the authoritative transaction commits. `qmsAuditRealtime.ts` handles occurrence-scoped connection/replay. The global Quality freshness coordinator starts that stream only on audit-occurrence routes, preventing Live Audit traffic from coupling People, Assurance, Intelligence or register workspaces.

### Offline

Internal employee Live Audit work reuses the encrypted portal mutation outbox. Online recovery replays governed QMS mutations idempotently and surfaces conflicts/failures rather than silently discarding them.

External guest-cookie sessions do **not** reuse this employee bearer-token outbox. A separate guest-specific encrypted replay contract is required before external-auditor offline work can be enabled safely.

### Findings and disclosure

Official finding creation remains atomic with the canonical finding/CAR workflow.

External auditors have a separate attributable **draft** lifecycle. Drafts can be submitted, returned/revised, withdrawn and promoted/reviewed by Quality into the canonical official finding workflow. They are not official findings until that governed promotion occurs.

`LiveFindingReleasePanel.tsx` provides an explicit release boundary. The auditee projection includes only released findings/evidence; private auditor notes and draft findings are not serialized to the external client.

## External document exchange

Guest submissions are append-only evidence records with safe filename, content type, byte size, SHA-256, participant identity, response comment, private storage locator and creation time.

The external read model is server-filtered and audit-bound. It exposes only granted audit identity/scope/criteria, optional progress, document requests, released findings/evidence, acknowledgement state and issued-report availability.

## Closing architecture

`AuditClosingWorkspace.tsx` composes a deterministic report from canonical audit state. Generation requires governed fieldwork completion and records frozen source/artifact hashes, template/renderer versions, actor/time and private storage reference.

Generated composition is adopted into the existing report revision lifecycle rather than creating a competing issue engine.

### Approval and signature

The existing report approval/issue lifecycle remains authoritative. Closing assurance adds electronic signature evidence over the exact issued report using:

- `PASSWORD_REAUTH`;
- signer identity;
- report revision ID and SHA-256;
- reason;
- nonce and timestamp;
- HMAC signature digest;
- configured failed-attempt/rate-limit policy.

This is **not** WebAuthn/passkey signing and must not be represented as such.

### Output policy

Versioned policy controls whether a closing occurrence may generate:

```text
NONE
REPORT_ONLY
APPROVAL_LETTER
CERTIFICATE
ATTESTATION
```

A generated assurance artifact retains report/signature/policy integrity lineage and its own checksum.

### Auditee issued-report receipt

The auditee workspace exposes only the latest formally `ISSUED` report. Download verifies the controlled path and SHA-256 before release.

Receipt acknowledgement is idempotent and appended to the existing external-access event ledger with participant identity, exact report revision ID/hash and timestamp. The acknowledgement records receipt without waiving response, corrective-action, review or appeal rights.

## Follow-up architecture

CAR/CAPA remains the governed #499 control loop: sharing, RCA/CAP, Quality accept/return/reject, reminders, escalation, risk-controlled extension, effectiveness and close authority all remain there.

Audit execution closure remains separate from assurance follow-up completion.

## Archive architecture

Archive governance extends the existing archive/evidence domain with:

- versioned retention policy revisions;
- immutable manifest inventory carrying authoritative record IDs/revisions and content hashes;
- generated package filename/size/SHA-256;
- append-only legal-hold placement/release;
- disposition request/approval/rejection/execution history;
- actor/reason and package/inventory integrity evidence.

Archive is the final occurrence workspace, not a deletion shortcut.

## Database and security controls

New external-access, fieldwork-sync, closing-assurance and archive records are tenant-bound. PostgreSQL all-head validation exercises RLS/FORCE RLS, append-only/immutability constraints, attribution and package integrity.

The historical Workforce `applicability_json` migration includes a schema-aware guard because clean multi-head upgrades can legitimately encounter that column from an earlier head. The guard is required for `alembic upgrade heads` compatibility and does not alter the QMS domain model.

## Deliberately not duplicated

This branch does not create replacement engines for programme/risk planning, scheduling/conflicts, notice governance, checklist template governance, canonical checklist semantics, official finding/CAR association, CAR/CAPA milestones/escalation/effectiveness, formal report revision transitions, or execution-close/follow-up separation.

## Remaining hardening, not missing core architecture

1. Guest external-auditor offline replay needs its own session/CSRF-safe encrypted contract.
2. A dedicated simultaneous two-internal-browser E2E would strengthen realtime proof.
3. A dedicated evidence-link open/download E2E would strengthen evidence proof.
4. A dedicated adversarial direct-object/IDOR suite would strengthen already-proven tenant/RLS boundaries.
5. WebAuthn/passkey signing remains a future enhancement; current signing is explicitly `PASSWORD_REAUTH`.
