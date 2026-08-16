# QMS Live Audit execution checkpoint

This branch implements the uploaded Live Audit execution specification incrementally on top of the current governed Quality workflows. It does not replace the merged Audit Programme, checklist, report, CAR/CAPA or closeout state machines.

## Implemented

- Six-stage authoritative audit-session projection: Setup, Prepare, Live, Closing, Follow-up, Archive.
- Focused Live Audit checklist workspace using canonical response vocabulary.
- Versioned, idempotent internal fieldwork mutation receipts with device sequencing and client capture timestamps.
- Encrypted portal outbox reuse for offline checklist updates and atomic finding intents.
- Stale-version conflict rejection; no silent last-write-wins.
- Durable Quality audit events committed with fieldwork writes and published through the existing realtime broker only after commit.
- Atomic internal finding + checklist response + task + CAR transaction.
- Released-only auditee external view and explicit finding release/withdraw boundary.
- Secure auditee document submission and Quality review/download.
- First-class external auditor identity/grant model with bounded assigned-audit checklist execution.
- External-auditor participant attribution; no fake employee accounts.
- External auditor notes/evidence retained as append-only participant contributions separate from internal Quality notes.
- External audit session CSRF token for write operations.
- Fail-closed Email Link assurance until a real MFA/passkey ceremony is integrated.
- Immutable external-auditor finding draft revisions with CREATED, SUBMITTED, RETURNED, WITHDRAWN and reserved PROMOTED lifecycle event.
- External auditor save/submit/revise/withdraw UI and Quality return-for-revision component.
- Deterministic generated closing report artifact with frozen snapshot and hashes while preserving the governed report issuance lifecycle.

## Deliberately incomplete

- Quality promotion of an external draft into an official finding remains disabled until both internal Live Audit and external draft promotion call the same no-commit official finding/CAR transaction service.
- The Quality external-draft review component still needs to be mounted in the Live Audit host.
- External-auditor offline replay is not yet enabled because the employee bearer-token outbox cannot be reused blindly for cookie/CSRF guest sessions.
- WebAuthn/e-signature is not yet implemented; MFA/PASSKEY labels are rejected rather than falsely asserted.
- Policy-driven NONE / REPORT_ONLY / APPROVAL_LETTER / CERTIFICATE / ATTESTATION artifact generation remains.
- Archive manifest, retention class, legal hold and controlled disposition remain.
- Full 45-scenario browser acceptance remains.

## Security posture

New external audit tables use tenant RLS/FORCE RLS. Access, release, submission, report artifact, fieldwork receipt/contribution and external finding draft histories are append-only or immutable where applicable. Existing repository dependency advisories remain a separate merge gate and are not suppressed by this implementation.
