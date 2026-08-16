# QMS Report and Signature Lifecycle

## Governing rule

The existing report governance remains authoritative:

```text
DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED → SUPERSEDED
```

The Live Audit work changes how the draft artifact is produced. It does not weaken formal review/approval/issue controls.

## Current generated-report implementation

`audit_report_composition.py` builds a canonical snapshot from:

- audit identity/scope/criteria;
- actual/planned dates;
- assigned audit team identifiers;
- governed checklist execution;
- findings;
- linked CARs;
- preparation document-request state.

Generation is blocked unless:

- fieldwork has `actual_end`; and
- no checklist execution row remains `NOT_VERIFIED`.

The source snapshot is canonical-JSON hashed with SHA-256. The server renders a PDF using the existing ReportLab dependency and stores:

```text
source_snapshot_hash
template_version
renderer_version
filename
content_type
size_bytes
artifact_sha256
private storage_ref
generated_by_user_id
created_at
```

Generated artifacts are append-only and tenant-RLS protected.

## Important semantic boundary

`report.generated` does not mean `report.issued`.

The Closing workspace displays three distinct positions:

```text
Generated artifact
→ Governed report revision
→ Issued report
```

The branch currently stops after generation. Automatic adoption of the generated artifact into the existing report-revision lifecycle is still pending.

## Required adoption transaction

The next report-domain step must:

1. Load the selected generated artifact under tenant scope.
2. Verify its stored SHA-256 against the private file.
3. Create a new governed report revision in `DRAFT` using the generated artifact as the controlled source.
4. Preserve `source_snapshot_hash`, artifact hash and renderer/template metadata in revision/evidence lineage.
5. Append the existing report-governance event.
6. Avoid setting any compatibility field that causes the authoritative workflow to infer `report_complete` before formal issue/approved state.
7. Return the existing report-revision representation.

Do not recreate the report state machine in the composer.

## Closing-meeting target

Normal successful path:

```text
fieldwork complete
→ generate deterministic draft
→ review closing narrative
→ auditee acknowledgement/comments
→ submit for internal review
→ Quality approval
→ electronic signature
→ issue immutable revision
→ share report/CARs
→ close audit execution
```

## Electronic signature

Historical PR #280 contains reusable concepts for:

- WebAuthn/passkeys;
- explicit signing intent;
- artifact-hash binding;
- signer evidence bundles;
- public verification token;
- provider abstraction;
- distinction between appearance-only and stronger cryptographic/PAdES signing.

It must not be merged wholesale because it predates current Quality architecture.

Current branch state:

**Electronic signature is not integrated.** The Closing UI deliberately displays this as incomplete.

## Signature requirements when ported

Every signature must bind:

```text
signer identity
signing authority/capability
artifact ID
artifact SHA-256
report revision ID
signing reason
signature provider/assurance level
server timestamp
verification/evidence bundle
```

An appearance stamp must never be presented as a cryptographic PAdES signature.

## Certificate / approval output policy

Do not issue a certificate for every audit.

Required policy vocabulary:

```text
NONE
REPORT_ONLY
APPROVAL_LETTER
CERTIFICATE
ATTESTATION
```

The policy is audit-type/programme controlled. If numbering, validity or approving authority is not configured, artifact generation must fail closed rather than inventing business rules.

## Incomplete items

- Generated artifact → existing report revision adoption.
- Closing narrative/editor model separate from immutable source facts.
- Auditee closing acknowledgement flow beyond finding acknowledgement.
- WebAuthn/passkey/e-signature port.
- Signature verification page integration.
- Policy-driven approval/certificate artifact.
- Same-day full browser acceptance from fieldwork completion to signed issue.
