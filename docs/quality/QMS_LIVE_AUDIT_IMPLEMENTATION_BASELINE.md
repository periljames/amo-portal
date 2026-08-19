# QMS Live Audit Implementation Baseline

Date: 2026-08-16  
Branch: `agent/qms-live-audit-operating-workspace`  
Acceptance contract: uploaded QMS Frontend Deep Research and Fullstack Execution Specification.

## Governing baseline

The branch preserves the existing QMS business state and compresses operator work around one occurrence. It does not create a second audit engine.

| Capability | Authoritative owner | PR #502 treatment |
|---|---|---|
| Audit workflow | Existing audit workflow contract | Project authoritative state through `SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE`; navigation never creates completion. |
| Programme / schedule | Audit Programme + Planner | Reuse existing planning/scheduling/conflict controls. |
| Preparation | Existing preparation revision and document-request governance | Add one Prepare workspace, guest document exchange, review and external participant controls. |
| Checklist execution | Existing checklist execution/governance | Add compressed Live workspace, idempotent sync, realtime/offline internal execution and scoped external-auditor contribution. |
| Findings | Existing official finding/CAR workflow | Preserve official transaction; add explicit release boundary and external draft→Quality review/promotion. |
| Report governance | Existing report revision lifecycle | Deterministically compose from audit state, adopt into existing lifecycle, approve/issue/sign without a parallel report engine. |
| Execution close / follow-up | Existing closure state | Preserve separate `AUDIT EXECUTION CLOSED` and `ASSURANCE FOLLOW-UP COMPLETE`. |
| CAR/CAPA | Governed #499 control loop | Preserve milestones, deadline decisions, escalation, effectiveness and close authority. |
| Archive | Existing archive/evidence domain | Add retention policy, immutable manifest/package integrity, legal hold and governed disposition. |
| Controlled documents | DMS / Document Control | Retain governed references/snapshots and controlled guest submissions rather than filesystem disclosure. |

## Implemented occurrence experience

### Setup / Prepare

- Additive occurrence deep links retain the existing route owner.
- First-class external participants/grants are tenant-bound, expiring and revocable.
- EMAIL_LINK invitation exchange produces an HTTP-only scoped guest session and removes the raw token from the browser URL.
- Auditee document requests/uploads and Quality review remain audit-bound.

### Live

- Canonical checklist responses and evidence are reused.
- Mutations carry idempotency/version/device metadata.
- Internal employee Live work supports encrypted offline queue/replay and conflict rejection.
- Audit occurrence routes subscribe to the QMS realtime stream; unrelated Quality workspaces do not.
- Auditees receive only explicitly released findings/evidence.
- External auditors execute assigned scope with participant attribution and CSRF-bound writes.
- External finding drafts remain drafts until governed Quality promotion/review creates an official finding through the canonical workflow.

### Closing

- Deterministic PDF composition records frozen source and artifact SHA-256 values.
- Generated composition is adopted into existing report revision governance.
- Electronic signature evidence is bound to the exact issued report using `PASSWORD_REAUTH`, signer identity, nonce, reason, timestamp and HMAC digest under rate-limit policy.
- Versioned output policy controls report-only / approval-letter / certificate / attestation behavior.
- The auditee can download and acknowledge the exact latest `ISSUED` report; acknowledgement is idempotent, append-only and revision/hash bound.

### Follow-up

- CAR/CAPA remains fully owned by the governed #499 loop.
- Audit execution closure does not falsely imply CAR/effectiveness completion.

### Archive

- Versioned retention policy.
- Immutable manifest inventory with authoritative record identifiers/revisions/content hashes.
- Archive package filename/size/SHA-256.
- Append-only legal-hold and disposition decision history.

## Public and compatibility routes

Internal stage links remain additive under the existing occurrence route:

- `/quality/audits/:auditRef/setup`
- `/quality/audits/:auditRef/prepare`
- `/quality/audits/:auditRef/live`
- `/quality/audits/:auditRef/closing`
- `/quality/audits/:auditRef/follow-up`
- `/quality/audits/:auditRef/archive`

Purpose-bound public routes include:

- `/qms/audit-access/:token`
- `/qms/audit-access`
- existing `/qms/car-access/:token`

The Vite SPA/proxy contract explicitly preserves signed public HTML deep links in both development and production preview.

## Security / validation baseline

The implemented code has dedicated contracts for session projection, external access/token/scope/CSRF, external drafts/promotion, guest document storage, deterministic report composition, idempotent fieldwork sync, realtime replay, closing assurance, issued-report acknowledgement and archive governance.

PostgreSQL all-head validation exercises RLS/FORCE RLS, attribution, append-only behavior and package integrity. Browser CI covers public access, auditee upload/acknowledgement, external auditor draft execution and responsive/accessibility behavior, with retained failure traces/logs.

The final merge decision remains exact-head based rather than relying on this document.

## Explicit remaining hardening

1. External-auditor guest-cookie offline replay requires a guest-specific encrypted session/CSRF-safe design; the employee bearer-token outbox is intentionally not reused.
2. Current electronic signing is `PASSWORD_REAUTH`, not WebAuthn/passkeys.
3. Dedicated two-internal-browser realtime, adversarial direct-object/IDOR and evidence-link open/download E2E suites would strengthen proof beyond the existing contracts.
