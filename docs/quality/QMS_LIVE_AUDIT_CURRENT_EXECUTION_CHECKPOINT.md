# QMS Live Audit execution checkpoint

PR #502 now implements the Live Audit execution specification on top of the governed QMS Assurance OS and CAR control loop. It does not replace the existing Audit Programme, checklist, finding, report, CAR/CAPA or closeout state machines.

## Implemented operating flow

### 1. Setup and preparation

- One audit occurrence projects through **Setup → Prepare → Live → Closing → Follow-up → Archive**.
- Internal auditor assignment, eligibility/independence controls, scheduling and notice governance reuse the existing QMS baseline.
- External auditors are first-class scoped participants; they are not represented as fake employee accounts.
- EMAIL_LINK external access is supported. MFA/PASSKEY labels fail closed until a real authentication ceremony exists.
- Auditees receive scoped document requests and can upload requested evidence through the secure external workspace.
- Quality can review/download submitted preparation documents without exposing internal-only audit state.

### 2. Live fieldwork

- Canonical checklist responses persist through versioned, idempotent fieldwork mutations.
- Internal mutations carry client mutation ID, device ID/sequence, client timestamp and base version.
- Stale writes are rejected instead of silently applying last-write-wins.
- Employee Live Audit work reuses the encrypted portal mutation outbox for offline queue/replay.
- QMS audit events are committed with authoritative writes and published through the existing realtime broker only after commit.
- Realtime subscription/replay is scoped to actual audit-occurrence routes; portfolio/People/Assurance/Intelligence pages do not inherit Live Audit replay behavior.
- Atomic internal finding intent uses the canonical official finding/CAR transaction rather than a parallel finding state machine.
- External auditors can execute only their assigned audit checklist, with participant attribution and CSRF-bound writes.
- External auditor notes/evidence are retained as attributable contributions separate from internal Quality notes.
- External finding drafts support create, submit, return for revision, revise, withdraw and governed promotion/review into the canonical official finding workflow.
- Auditees receive only explicitly released findings/evidence. Drafts and private auditor deliberations are not sent to the public read model.

### 3. Closing meeting and same-day output

- Closing report composition is deterministic from canonical audit state and records frozen source/artifact hashes.
- The existing governed report approval/issuance lifecycle remains authoritative.
- Electronic signature evidence is available for the exact issued report using **PASSWORD_REAUTH** with configured failure-rate limits, signer identity, report SHA-256, reason, nonce, timestamp and HMAC signature digest.
- This branch does **not** claim WebAuthn/passkey signing.
- Versioned output policy controls `NONE`, `REPORT_ONLY`, `APPROVAL_LETTER`, `CERTIFICATE` and `ATTESTATION` behavior.
- Policy-enabled assurance artifacts are generated from the issued report and signature evidence with their own checksum/integrity chain.
- The auditee secure workspace exposes only the latest formally `ISSUED` report. Download verifies the controlled path and SHA-256 before release.
- Auditee report receipt acknowledgement is idempotent and appended to the external-access ledger with participant identity, exact report revision ID/hash and timestamp. The acknowledgement explicitly records receipt and does not waive response, corrective-action, review or appeal rights.

### 4. Follow-up and CAR/CAPA

- CAR sharing, RCA/CAP submission, Quality return/reject/accept, reminders, escalation, controlled extensions, effectiveness review and final closure remain governed by the existing CAR control loop from #499.
- Audit execution may close while CAR/CAPA follow-up remains open, preserving the existing QMS separation between fieldwork completion and corrective-action lifecycle.

### 5. Archive governance

- Versioned retention policy revisions define retention class, start event, duration/indefinite retention, governing basis, review-before-disposition, legal-hold support and disposition mode.
- Archive manifests retain authoritative record IDs/revisions, source system, retention role and content hashes.
- Generated archive packages record package filename, size and SHA-256.
- Legal-hold placement/release is append-only.
- Disposition approval/rejection/execution is governed and retains inventory/package hashes and actor/reason history.

## Security and failure-handling posture

- New external audit, fieldwork, report and archive tables use tenant-aware controls; the PostgreSQL all-head probe proves RLS/FORCE RLS, attribution, package integrity and append-only behavior.
- Signed public workspace deep links remain React SPA routes in both Vite development and production preview; HTML navigation is not accidentally proxied to the API backend.
- Browser CI now retains Playwright traces/screenshots/test results and preview logs for Live Audit, External Draft, CAR and the key Operational UI paths instead of returning opaque exit-code failures.
- Historical Alembic heads can converge on the Workforce `applicability_json` column; the guarded Rostering migration is therefore retained as a required clean-`upgrade heads` compatibility measure, not an unrelated QMS feature.

## Verified baseline

On code baseline `2043d620f7b80316b647cb75b0be12b1a0dda5e4`:

- **QMS Live Audit CI** passed backend contracts, PostgreSQL `upgrade heads`, RLS/append-only/integrity probes, frontend lint/unit/build and public/responsive Chromium acceptance.
- **QMS External Draft CI** passed.
- **QMS CAR Control Loop CI** passed.
- **QMS Live Audit Security** passed.
- Platform dev-proxy, Assurance OS completion, Rostering control and Portal Error Feedback checks passed.
- QMS Operational UI passed People, Assurance, Intelligence, semantic regressions, Codex regressions, Missions and Control Room; the bounded-register step remained red and is being rerun with retained diagnostics on the newer head.

The final PR head must be revalidated after this documentation reconciliation before merge readiness is asserted.

## Deliberately not overclaimed

1. **External-auditor offline replay remains pending.** The employee encrypted outbox automatically carries employee bearer authentication and must not be reused blindly for guest cookie/CSRF sessions. A guest-specific replay contract is required before enabling this safely.
2. **WebAuthn/passkey signing is not implemented.** Current electronic signature evidence is explicitly `PASSWORD_REAUTH`.
3. **Cross-tenant RLS is proven**, but a dedicated adversarial direct-object/IDOR suite remains worthwhile hardening.
4. **Realtime is implemented and contract-tested**, but a dedicated simultaneous two-internal-browser acceptance test remains worthwhile.
5. **Evidence references are governed**, but a dedicated end-to-end evidence link/open/download acceptance test remains worthwhile.
