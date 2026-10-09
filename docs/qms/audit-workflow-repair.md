# Audit preparation and auditee CAP workflow repair

The blank preparation page was caused by generic Quality dispatch routes
intercepting focused preparation APIs and returning a successful response with
the wrong shape. Cached activity data could trigger a second rendering failure.
Exact workflow APIs now precede generic dispatch, preparation and lifecycle
responses are checked before rendering, and the workspace has a recoverable
error boundary with visible loading feedback.

Preparation drafts remain available while setup is incomplete. The readiness
controls distinguish issuing preparation from permission to start fieldwork.
Scope, assigned checklist and controlled-source changes invalidate preparation;
execution dates, record versions and fieldwork answers do not. Existing immutable
preparation revisions remain compatible without being rewritten. Fieldwork uses
the pre-fieldwork evidence requirements, and atomic finding creation retains the
sampled-item details through the supported execution update.

Work-package snapshots normalize dates, meeting times, UUIDs and other supported
JSON values before hashing and database persistence. This fixes the observed
preparation-issue failure when a scheduled audit includes time-of-day values;
the package hash describes the same JSON representation that is actually stored.

Auditees can open their authorized CAR response from the shared audit workspace,
load related responses, retain unfinished CAP drafts in their browser tab, retry
evidence loading, preview and submit, and recall a submission before review.
Returned responses can be corrected and resubmitted. Canonical and compatibility
narratives are synchronized, concurrent submissions and review/recall operations
lock the CAR row, and controlled deadlines require the extension workflow.

Quality reviewers explicitly choose their RCA and CAP decisions. Recorded
responses and decisions update the corresponding staged CAR milestones, including
when the staged workflow is initialized after a response already exists.
Accepting a plan keeps a staged CAR open for implementation, evidence verification
and effectiveness review. Verified staged closure remains a separate operation.
Closing, follow-up and archive actions refresh the occurrence and session state.

Preparation navigation, readiness messages, CAP response controls and controlled
document references have been improved. Reference cards show document identity,
revision and filename, with exact file verification available on demand. The
portal uses its own application icon rather than unused framework assets.

## Verification and data preservation

The production frontend build and Python compilation passed. The restarted API
started successfully, and the actual audit's session, readiness, preparation
context, activity, closure and report-revision APIs returned their expected
contracts. The supplied preparation URL rendered without JavaScript errors or
failed HTTP responses during the final read-only browser check. Extended test
runs were stopped in accordance with the request to prioritize completing code;
the final changes have not been verified through a full end-to-end lifecycle.
The work-package snapshot was also built from the actual saved preparation in a
read-only transaction and serialized successfully, including its scheduled
start and end times.

The database review checked 641 Quality foreign-key relationships and found no
orphaned records, unvalidated constraints, duplicate audit/CAR references or
cross-tenant relationship mismatches. Existing audits, users, controlled documents
and evidence were preserved. Two generated test files were removed only after
confirming they had no document/revision database references. Unused repository
archives, generated directory listings and obsolete browser artifacts were
removed; useful investigation reports were moved into `history/`.

This repair does not issue a real audit revision, approve a CAP, create audit
evidence or complete an audit on behalf of the responsible people. Those are
governed actions performed through the repaired workflow with the actual records.
