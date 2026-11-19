# CAR workflow and usability verification — 30 October 2026

## Changes

- Milestone controls stack into labelled cards on small screens. Server refreshes
  preserve edited fields while adopting changes to untouched fields.
- Initialization displays the authoritative deadline as read only; deadline
  extensions remain controlled requests with recorded decisions.
- Action review uses compact responsive cards, readable dates, owner names where
  available, evidence filename downloads and explicit decision status.
- Review rationale is validated before submission. Confirmed decisions remain
  visible if a subsequent refresh fails. Closed cases suppress editing controls.
- Overview facts use separated labels and values. New review decisions start
  with empty notes; previous reasons remain available separately, preventing an
  old rejection reason from being silently reused for acceptance. Return and
  evidence-request controls require a reason before Save is enabled.
- Pending submission displays “Submitting…” instead of prematurely claiming
  that the response is locked.
- Feedback separates send errors from refresh errors, preserves drafts and retry
  receipts, identifies shared versus internal messages, and shows stream health.
- Legacy CAR edits and the common closure transition establish PostgreSQL tenant
  context before querying protected governance records. Audit logging accepts
  string status values produced by transitions.

## Evidence and limits

The live case is the explicitly marked synthetic `QA-CAR-LIVE-F6A59B` in the
existing tenant. The requested auditor account retains its existing permissions;
its roles were not elevated. No operational CAR was used for test decisions.

Twelve production-build browser regression scenarios passed after correcting one
accessible-name locator in the control-loop test. They cover draft preservation,
action evidence download, mobile width, role gates, closed-case controls and
retained send errors. These use API fixtures and do not prove live closure.
Desktop and phone screenshots of action reviews and milestone controls were
visually inspected. Native computer-use access was unavailable, so browser
verification used the repository's Playwright suite and rendered screenshots.

Live shared auditor feedback appeared in the invited respondent view without a
reload. Private notes were excluded from both public DOM and public API data;
public entries omit actor user IDs. The deliberately interrupted acknowledgement
retained the draft and allowed a retry. The auditor received that reply and a
read-only database query confirmed exactly one row for its unique QA receipt.
The follow-up public history request timed out during a period of HTTP 503s, so
the complete browser scenario was not a clean pass.

A subsequent negative closure check exposed a real legacy endpoint failure:
missing tenant context hid protected control records, and string status audit
serialization raised HTTP 500. Targeted regression coverage was added for this
boundary. Sixteen targeted governance tests passed. The final frontend build
passed modal checks, TypeScript, Vite and heavy-route checks; targeted lint passed.
Public deployment serves `index-BcybaD5Z.js`.

After deployment, the browser's legacy and tenant-prefixed closure attempts,
governed deadline edits and manufactured closure timestamp all returned the
expected HTTP 409. Saving invitation expiry from a non-UTC browser retained the
exact UTC instant. The actual auditor review dialog was visually inspected.
Rejection committed both RCA and CAPA decisions, reasons and the shared message;
the test's response wait expired before the successful HTTP 200 arrived. A
read-only database check confirmed the retained rejection. Auditee rework saved
RCA, revised the existing accountable action, uploaded evidence and resubmitted.
The revised response was then read from the auditor endpoint and displayed in the
actual control page. The first immediate check had raced submission because the
UI displayed a locked response while the save was still pending. Pending copy
now says “Submitting…”; the acceptance test waits for the actual committed PATCH
response and closed preview before asserting submission. The auditor subsequently accepted the RCA and CAPA through the review dialog.
The first two lifecycle milestones were accepted; premature closure still failed.
The individual action was returned, revised by the auditee while the accepted
narrative remained locked, approved, progressed, submitted with the uploaded CAR
file and independently verified. The implementation and evidence milestones
were accepted. The reviewer adopted the effectiveness proposal through Quality
controls into an actual Assurance Case.

The final resumed closeout phase **passed** (29.1 seconds; 33.7 seconds including
runner startup). The appointed reviewer recorded an immutable EFFECTIVE
conclusion through the assurance form, accepted the last milestone and closed
through the governed CAR controls. The invited view received the read-only
closure state without a reload. Shared history retained rejection, acceptance
and effectiveness; private notes stayed excluded. The 390-pixel public closure
page did not overflow. Revoking the synthetic invite returned HTTP 410 for both
its former main and draft endpoints, while the CAR remained CLOSED. No server
errors or page errors occurred in this final resumed phase.

Verification resumed committed checkpoints rather than reseeding or replaying
previous decisions. This is evidence of the individual live stages and a clean
final closeout phase, not a claim that a fresh uninterrupted full-lifecycle run
passed. Earlier attempts encountered timeouts and HTTP 502/503 responses.

Additional visual findings: the public implementation table clipped content,
overview facts lacked label/value spacing, and the Assurance Cases link vanished
on reload. Responsive public action cards, spaced facts and a persistent
assurance navigation link address these issues. The final source changes require
production-build browser regression and deployment verification below.

VM diagnostics showed network link interruptions and high Windows host memory
pressure; PostgreSQL had ample guest memory and no swap use. Direct and public
history probes recovered afterward. These observations do not establish the
underlying cause or sustained network stability.

Private bearer fixtures, logs and screenshots remain in ignored `.artifacts` and
`frontend/test-results`; they must not be committed.
