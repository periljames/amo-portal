# Reliability Operational Sources

## Purpose

The Reliability module owns controlled source registers for operational evidence that was previously represented only by adapter contracts. Each register is tenant-scoped, revisioned, approval-controlled and linked to the immutable canonical Reliability ingestion ledger.

## Source registers

| Source code | Controlled register | Canonical trigger |
|---|---|---|
| `FLIGHT-OPERATIONS` | Technical interruptions including delays, cancellations, return-to-gate, turnback, diversion, in-flight shutdown and aborted take-off | Approval and closure revisions |
| `MEL-CDL` | MEL/CDL application, approved basis, procedures, repeat-inspection interval, extension history, expiry and closure evidence | Approval, extension, automatic expiry and closure revisions |
| `COMPONENT-SHOP-FINDINGS` | Incoming component identity, approved test result, confirmed-failure/NFF decision, disposition and release reference | Approval and release revisions |
| `SMS-EVENTS` | Safety occurrence and accountable Reliability relevance assessment | Positive relevance assessment |
| `QMS-FINDING-LINKS` | Selected QMS finding with objective evidence and technical relevance reason | Explicit link action |
| `WORKBOOK-HISTORY` | Original workbook, mapping profile, row validation and row-level decision | Approved import and approved rows only |
| `WORKPACK-TASKS` | Non-routine findings raised during scheduled maintenance | Existing workpack harvest with scheduled-check provenance |

## Integrity controls

- Every operational record has a stable source identifier and an incrementing revision.
- Revision actions are stored in `reliability_source_revision_events`; PostgreSQL blocks update and delete operations on that table.
- Aircraft and component references are validated inside the active tenant.
- NFF records require `confirmed_failure=false`.
- MEL/CDL expiry cannot precede application; extensions require a later expiry, reason and approval reference.
- The Reliability scheduler records expired deferrals and retries approved records that have not reached the canonical event ledger.
- SMS records create Reliability events only after an accountable positive relevance assessment.
- QMS findings are linked individually rather than copied wholesale.
- Historical workbook rows retain original values, SHA-256 hashes, mapping output, validation results and human decisions.
- Direct adapter ingestion routes are not registered for internally owned sources; operational approval workflows are the write path.

## Exact aviation values

Regulated flight-hour and component-life columns are migrated from binary floating-point storage to exact PostgreSQL values:

- Hours and life values: `NUMERIC(20,3)`.
- Cycles and landings: `BIGINT`.

The migrations reject fractional cycle values rather than silently rounding them. SQLAlchemy bindings convert through decimal strings and require whole-number counts.

## User workflow

The tenant Reliability workspace exposes **Operational sources** with:

- source readiness and available-versus-ingested counts;
- Flight Operations creation, approval and closure;
- MEL/CDL creation, approval, extension and closure;
- component-shop finding/NFF approval and release;
- SMS relevance assessment;
- explicit QMS finding linkage; and
- workbook upload, mapping, row reconciliation, import approval and ingestion.

## Interaction and derivation rules

The operational interface follows source workflows rather than exposing database fields directly:

- Active aircraft are selected from the tenant fleet register instead of typing serial numbers repeatedly.
- For a technical delay, the user records scheduled and actual departure. Delay minutes are derived by the API and shown by the interface; they are not a second editable fact.
- The API rejects an actual departure before the scheduled departure and rejects any supplied delay or dispatch impact that conflicts with the derived values.
- Technical cancellations require the scheduled departure and cannot contain an actual departure.
- Operational impact is derived from the selected occurrence type, while severity remains an accountable classification.
- MEL/CDL expiry is entered from the approved item basis. The interface does not invent a generic expiry interval.
- Repeat-inspection intervals may be entered in practical units and are normalised to minutes before storage.
- NFF classification fixes confirmed failure to `false`; a shop release reference is recorded only during the release action.
- SMS records are presented first as a relevance-assessment queue. A canonical Reliability event is created only for an affirmative assessment with a reason.
- QMS linking uses searchable controlled findings and displays the source evidence before linking; users do not paste opaque finding IDs.
- Workbook mapping uses guided source-column selection instead of requiring users to write JSON.
- Approval, extension, assessment, release, rejection and closure actions use controlled forms rather than browser prompt dialogs.
