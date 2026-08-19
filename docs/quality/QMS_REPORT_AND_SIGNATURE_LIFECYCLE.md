# QMS Report and Signature Lifecycle

## Governing report lifecycle

The existing report governance remains authoritative:

```text
DRAFT → INTERNAL_REVIEW → APPROVED → ISSUED → SUPERSEDED
```

Live Audit changes how the controlled draft is composed and signed. It does not create a second report state machine.

## Deterministic report composition

`audit_report_composition.py` builds `QMS_AUDIT_REPORT_SNAPSHOT_V2` from authoritative occurrence data:

- audit identity, scope and criteria;
- planned and actual dates;
- assigned audit-team identifiers;
- persisted management summary, conclusion and positive-practices statement;
- non-cancelled occurrence meetings;
- governed checklist execution;
- findings;
- linked CARs;
- preparation request state.

Generation fails closed unless:

- fieldwork has `actual_end`;
- no checklist execution row remains `NOT_VERIFIED`;
- management summary is populated;
- audit conclusion is populated;
- a positive-practices statement is populated, including an explicit statement when none were observed.

The canonical JSON snapshot is SHA-256 hashed. The generated PDF records source-snapshot hash, template/renderer version, filename, media type, size, artifact SHA-256, private storage reference, generating user and timestamp.

`report.generated` is not `report.issued`.

## Adoption into the governed report domain

The Closing workspace now performs the controlled transaction:

```text
deterministic generated artifact
→ governed DRAFT report revision
→ auditee closing response
→ INTERNAL_REVIEW
→ APPROVED
→ WebAuthn signature evidence
→ ISSUED
```

The generated artifact is verified and adopted as a governed revision. Formal review, approval and issue remain in the existing report lifecycle.

## Auditee closing response

When an auditee participant exists, the exact governed draft revision and SHA-256 are exposed through the purpose-bound closing context. The auditee may record:

- `ACKNOWLEDGED`;
- `COMMENTED`;
- `DECLINED_TO_ACKNOWLEDGE`.

Comments are required for comment/decline responses. The record is append-only and bound to the exact draft revision/hash.

This is a closing-meeting response, not a waiver and not automatic acceptance of findings.

Issued-report receipt is a separate record against the exact issued revision/hash.

## WebAuthn / passkey approval

The canonical Closing flow uses WebAuthn/passkey evidence for approval of the exact `APPROVED` report revision.

The ceremony binds:

```text
tenant
audit
report revision ID
artifact SHA-256
signer identity
signing reason
credential ID hash
WebAuthn sign count
origin
RP ID
ceremony SHA-256
server timestamp
```

User verification is required. The server refuses `ISSUE` when current passkey evidence is absent, stale, belongs to another revision/hash, or predates the current approval state.

Password re-authentication is not represented as equivalent passkey evidence in the canonical closing workflow.

## Immutable issue

After issue:

- the governed report revision is `ISSUED`;
- its exact revision/hash is the public and auditee reference point;
- execution closure remains separate from CAR/CAPA follow-up;
- a new return/reapproval path requires fresh valid signature evidence where the lifecycle permits revision change.

## Policy-controlled assurance output

Assurance output is not automatic for every audit. The governed policy vocabulary remains:

```text
NONE
REPORT_ONLY
APPROVAL_LETTER
CERTIFICATE
ATTESTATION
```

Where a supplementary artifact is permitted, it is generated from the governed report/signature evidence and carries its own integrity metadata. Missing policy/authority rules fail closed rather than being invented by the UI.

## Public verification

A high-entropy public verification token may be created for an issued report. The raw token is returned only to the creator and is stored server-side only as a SHA-256 hash.

The verification surface can expose the report revision/hash and passkey/assurance metadata without publishing the controlled report itself. A user may calculate a local file SHA-256 in the browser and compare it with the governed value without uploading that file.

## Closing sequence

The intended same-occurrence sequence is:

```text
complete fieldwork
→ save closing narrative
→ conduct closing meeting
→ release findings/CARs as authorised
→ generate deterministic report
→ adopt governed draft
→ auditee closing response
→ submit for review
→ Quality approval
→ passkey signing
→ immutable issue
→ optional policy-controlled assurance output
→ create verification link if required
→ close audit execution
→ continue CAR/CAPA follow-up independently
```

## Validation status

This document describes the current source implementation on PR #502. It does not assert that the current head has passed typecheck, migrations, browser acceptance or full CI. Those checks belong to the post-freeze validation phase.
