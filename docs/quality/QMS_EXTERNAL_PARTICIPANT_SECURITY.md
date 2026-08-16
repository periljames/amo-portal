# QMS External Participant Security

## Security objective

External auditors and auditee representatives must participate in a specific audit without being created as tenant employees and without receiving a broad internal Quality object.

## Principal types

```text
INTERNAL_USER
EXTERNAL_AUDITOR
AUDITEE_GUEST
```

Current external browser exchange is implemented for purpose-bound guest access. External-auditor edit capabilities are modelled but must not be treated as complete until authenticated write routes are bound to the same participant contract.

## Identity assurance

Database vocabulary permits:

```text
EMAIL_LINK
MFA
PASSKEY
```

**Current enforced implementation:** `EMAIL_LINK` only.

The API rejects creation of MFA/passkey access because no current-main assurance ceremony has been integrated yet. The historical #280 passkey/WebAuthn work is reusable source material, not evidence that current QMS guest access is passkey-protected.

## Invitation/grant token

The invitation is an HMAC-SHA256 signed envelope containing:

- token version;
- tenant identifier;
- grant identifier;
- expiry epoch;
- high-entropy nonce.

Security sequence:

1. Validate token structure.
2. Validate HMAC with constant-time comparison.
3. Validate expiry/version/nonce.
4. Only then set PostgreSQL tenant context from the signed tenant value.
5. Query grant by grant ID, tenant and SHA-256 token hash.
6. Verify participant, identity, expiry and revocation state.

The database never stores the raw invitation secret.

## Browser exchange

`POST /quality/audit-access/exchange`

On successful exchange:

- the raw invitation token is accepted once;
- an attributable access event is appended;
- an HTTP-only, strict-SameSite audit guest cookie is issued;
- the frontend immediately removes the raw token from the URL;
- subsequent requests use the HTTP-only session.

Employee login/session expiry does not redirect the external audit workspace into the tenant login flow.

## Permission allowlists

Auditee guest maximum vocabulary:

```text
audit:read_summary
audit:read_progress
audit:read_released_findings
audit:read_released_evidence
audit:document_submit
audit:acknowledge
car:respond
```

External auditor maximum vocabulary:

```text
audit:read_assigned
audit:read_summary
audit:read_progress
audit:checklist_execute
audit:evidence_create
audit:finding_draft
audit:report_contribute
```

Unsupported permissions fail closed.

## Released-data rule

The external read model is constructed server-side. It never relies on CSS/React hiding.

Auditee-facing findings require an explicit latest release event:

```text
RELEASED
WITHDRAWN
```

Recording a finding is not disclosure. Private auditor notes remain excluded even when the finding is released. Objective-evidence text is included only when the release decision explicitly permits it. Released file/evidence references have a separate allowlist.

## Document submission controls

Guest submissions:

- derive tenant/audit/participant from verified grant;
- cannot submit to arbitrary tenant/audit IDs;
- block accepted/waived requests;
- enforce bounded file size;
- enforce an extension allowlist;
- validate binary signatures for PDF, Office and image formats;
- sanitize filenames;
- stream SHA-256 while saving;
- store content under a private server-owned root;
- prevent traversal outside the root;
- expose metadata/download through authorised endpoints only.

## PostgreSQL controls

External identity, participant, grant, access history, finding-release and document-submission tables are tenant-owned and configured for RLS + FORCE RLS. Access/release/submission histories are append-only in PostgreSQL.

## Revocation

Revoking a participant:

- changes participant state to `REVOKED`;
- records `revoked_at`;
- revokes every active grant;
- appends a revocation access event;
- causes subsequent guest token/session checks to fail.

## Explicit incomplete controls

- MFA/passkey external identity assurance is not implemented.
- Guest session rate limiting is not yet QMS-specific.
- External-auditor write routes are not yet fully bound to participant capabilities.
- Realtime guest streaming is not yet implemented; current external view refreshes through the released-data HTTP projection.
- CSRF protection relies on strict SameSite plus purpose-bound route semantics today; a dedicated anti-CSRF token should be evaluated before broader guest mutations are added.
