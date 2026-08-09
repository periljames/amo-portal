# Formal Reliability Report Publication Control

## Purpose

This control defines how a formal Reliability Programme report moves from a working engineering review into a retained controlled publication. It is an implementation-control document, not a declaration of authority approval or regulatory compliance.

The authoritative state is the machine-readable formal report/profile/requirement data and retained publication evidence in the portal database.

## Lifecycle

`DRAFT -> DATA_REVIEW -> TECHNICAL_REVIEW -> QUALITY_REVIEW -> APPROVAL_PENDING -> APPROVED -> PUBLISHED`

Retained terminal states:

- `SUPERSEDED`
- `WITHDRAWN`

A published revision is immutable. A correction is a new draft revision referencing the prior publication; the prior revision is later explicitly marked `SUPERSEDED` when the controlled replacement is issued.

## Controlled freeze

Before controlled review can advance, the report freezes:

- reporting period;
- data-cutoff timestamp;
- fleet/effectivity selection;
- selected regulatory profile/version;
- requirement-version manifest;
- controlled source-record population and source-population SHA-256;
- governed calculation snapshot;
- formula revision catalogue;
- chart data;
- data-quality warnings.

A source event created or changed after the retained cutoff cannot be allowed to silently change the retained report revision.

## Completeness gate

The automated gate checks at least:

- profile/version retained;
- effectivity frozen;
- data cutoff frozen;
- source-population identity retained;
- governed calculations retained;
- formula revisions retained;
- required chapters ready or governed not-applicable;
- mandatory applicable requirements not `GAP`;
- `WITHHELD` conditions dispositioned according to the profile;
- retained HTML generated and SHA-256 stored;
- retained PDF generated and SHA-256 stored.

A mandatory unresolved requirement blocks approval/publication.

## Exceptional override

There is no hidden administrator bypass.

An allowed exceptional disposition requires a separate retained override record containing:

- failed check code;
- linked requirement where applicable;
- justification;
- authority/approved-programme basis;
- approving identity;
- approving role;
- report hash;
- timestamp.

An override does not rewrite the underlying requirement or make missing evidence disappear from report history.

## Separation of duties

Configured review roles are retained from the portal identity/RBAC model rather than hard-coded names. The baseline workflow separates technical review, quality review and approval. A non-superuser preparer cannot approve or publish the same revision they prepared.

System/AI accounts cannot review, approve or publish a formal Reliability report.

## Retained artifacts

Generation creates:

- retained HTML;
- HTML SHA-256;
- retained PDF;
- PDF SHA-256;
- PDF size;
- source-population identity;
- formula/calculation/chart snapshots.

Artifact retrieval verifies the retained hash before serving the HTML/PDF. A mismatch is treated as an integrity failure rather than silently serving altered evidence.

## Distribution

The initial controlled distribution channel is authenticated portal distribution. A distribution event retains:

- report ID;
- revision;
- report hash;
- recipient user/role or external controlled reference;
- channel;
- distributing user;
- timestamp;
- acknowledgement where supported.

New distribution is permitted only for the current `PUBLISHED` revision. Superseded reports remain accessible as retained historical evidence but must be visibly identified as superseded.

Future email delivery must use the portal's central notification infrastructure. Reliability must not create a parallel email subsystem.

## Supersession

A superseding revision:

1. starts as a new `DRAFT`;
2. increments the controlled revision;
3. links `supersedes_report_id` to the earlier retained publication;
4. obtains a new cutoff/effectivity/calculation/render/approval chain;
5. is published only after its own completeness/review controls pass;
6. leaves the prior report accessible but explicitly `SUPERSEDED`.

Historical HTML/PDF, hashes, requirements, calculations, approvals and distributions are not destroyed.

## Deterministic rendering

Formal report rendering consumes the frozen governed report snapshot only. It does not recompute dashboard mathematics.

Missing or unavailable denominators are displayed as `WITHHELD`; they are never converted to a misleading zero percentage.

The PDF renderer is configured for invariant/deterministic output from an identical retained snapshot. Hash retention remains the final artifact-identity control.

## Operational limitations still requiring completion

Before this PR can be marked ready for review, the implementation must still prove the full specified acceptance path, including formal six-month/annual browser UAT, long-term bounded trend aggregation, complete chapter/chart coverage, tenant isolation/RBAC negative cases, source-after-cutoff immutability, supersession visibility, and exact-head CI after final main reconciliation.
