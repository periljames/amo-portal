# QMS Live Audit Runtime Configuration

## Purpose

This document defines the runtime configuration required by the governed live-audit completion implementation on PR #502. It covers passkey/WebAuthn ceremonies, governed audit evidence storage, public verification and the operating assumptions for external audit access.

The implementation is intentionally fail-closed for production passkey ceremonies when the relying-party configuration is incomplete. Configuration is not a substitute for validation; the current code-first phase deliberately defers CI and end-to-end proof until implementation is frozen.

## WebAuthn / passkey configuration

### `QMS_WEBAUTHN_RP_ID`

The WebAuthn relying-party identifier used for Quality approval and external-auditor passkey ceremonies.

Example:

```text
QMS_WEBAUTHN_RP_ID=portal.example.com
```

Requirements:

- Use the registrable domain or valid relying-party domain that serves the portal.
- It must be compatible with the browser origin used for the ceremony.
- Do not include a URL scheme, path or port.
- Production code refuses to start a QMS passkey ceremony when this value is absent.

### `QMS_WEBAUTHN_EXPECTED_ORIGINS`

Comma-separated exact origins accepted for the WebAuthn ceremony.

Example:

```text
QMS_WEBAUTHN_EXPECTED_ORIGINS=https://portal.example.com,https://quality.example.com
```

Requirements:

- Include the URL scheme.
- Include the port when a non-default port is part of the browser origin.
- No path is permitted.
- Keep this list narrow. Do not use wildcard origins.
- Production code refuses the ceremony when the current origin is not in this allowlist.

### `QMS_WEBAUTHN_CHALLENGE_TTL_SECONDS`

Lifetime for a one-time WebAuthn registration/signing/assertion challenge.

Default:

```text
300
```

Accepted implementation range:

```text
60-900 seconds
```

Challenges are tenant/actor/purpose bound, expire, and are consumed once. A report-signing challenge is additionally bound to the audit and exact governed report revision.

## Governed evidence storage

### `QMS_AUDIT_EVIDENCE_DIR`

Filesystem root for immutable audit evidence objects.

Default:

```text
uploads/qms-audit-evidence
```

Production requirements:

- Mount this path on durable controlled storage.
- Include it in the backup/recovery design appropriate to QMS records.
- Restrict direct web/server access. Files are served only through permission-checked application routes.
- Do not expose this storage root as a static public directory.
- Preserve the database metadata and filesystem object together; the SHA-256 in the database is the integrity reference.

### `QMS_AUDIT_EVIDENCE_MAX_BYTES`

Maximum bytes accepted for one governed evidence file.

Default:

```text
52428800
```

That default is 50 MiB. Configure the reverse proxy and application request limits so the effective upload limit is consistent.

The evidence layer currently permits the controlled extension set implemented by `audit_evidence_storage.py` and applies file-signature checks where a stable signature exists. Unsupported file types fail closed.

## Public audit verification

Public verification links are generated from high-entropy purpose-bound tokens. Only the token hash is persisted in `quality_audit_verification_tokens`.

The public verification surface is:

```text
/verify/:token
```

Its API projection exposes only governed verification facts:

- audit reference/title;
- issued report revision and SHA-256;
- passkey-signature method, time and ceremony hash;
- optional policy-controlled assurance artifact metadata;
- verification expiry;
- local hash comparison result.

It does not expose checklist notes, working papers, unreleased findings, participant private data or internal Quality deliberations.

Verification tokens can be revoked and expire independently of the underlying retained audit record.

## External audit access

### Email-link auditee access

Auditee guest access remains purpose-bound `EMAIL_LINK` access using an HTTP-only guest session after token exchange. The raw invitation token is removed from the browser address after successful exchange and is not copied into local/session storage by the frontend.

### External-auditor passkey access

An external auditor may be configured with `PASSKEY` assurance. In that case:

1. direct email-link session exchange is rejected;
2. the external identity must complete the dedicated WebAuthn registration/assertion ceremony;
3. WebAuthn user verification is required;
4. only then is the purpose-bound HTTP-only guest audit session activated.

`MFA` remains fail-closed until an actual MFA provider is integrated. The system does not treat an assurance label as proof.

## Offline guest fieldwork

External-auditor structured fieldwork can be queued in encrypted IndexedDB storage. The queue stores mutation intent only:

- audit and participant scope;
- idempotency identifier;
- device sequence;
- client timestamp;
- base version;
- canonical response;
- attributable notes/references;
- reason.

It does **not** persist the invitation token, guest cookie or CSRF value.

Before replay, the client obtains a fresh guest fieldwork projection/CSRF token and verifies that the current audit and participant match the queue scope. Cross-audit/cross-participant replay is refused. Version conflicts remain pending for deliberate reconciliation rather than being overwritten.

Binary evidence uploads remain online-only because an uploaded file must enter governed storage and receive a server checksum/immutable artifact identity before it can be referenced by the authoritative checklist record.

## Required deployment review before validation

Before the later CI/E2E phase, deployment owners must confirm:

1. the real production portal domain and origin allowlist;
2. HTTPS termination and forwarded host/scheme behavior reaching FastAPI;
3. durable evidence storage mount and backup policy;
4. upload/request size limits at proxy and application layers;
5. database migration ordering through the new live-audit completion, evidence and presence revisions;
6. retention/backup controls for WebAuthn credential public keys, signature evidence, report revisions and evidence metadata;
7. whether additional trusted origins are genuinely required for staging or disaster-recovery deployments.

Do not broaden an origin, scope, evidence-release or public-verification rule merely to make a test pass. Validation should prove the governed boundary implemented here.
