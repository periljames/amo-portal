# Change Control and approvals

This change addresses the prioritized Change Control workflow. It does not certify the rest of the portal against the MOPM; the outstanding specialist workflows remain in `qms-live-gap-review-2026-10-22.md`.

## Behavior

New capability and controlled changes use a versioned workflow. Required MOPM readiness gates cannot be removed or replaced by a smaller custom gate set. Gate passage requires a retained, same-tenant evidence asset, human review findings and an attributable reviewer. Positive decisions recheck retained evidence availability and its recorded checksum. The portal does not infer regulatory acceptability from a file's existence or generate an SMS risk assessment.

Quality self-evaluation, the named Accountable Executive's decision, written Authority notification, Authority acceptance, implementation and effectiveness review remain distinct. The tenant administrator has operational access; a decision must still be recorded by its assigned Quality owner or executive. Recording an Authority letter does not close the change. Implementation records an actual date, evidence and confirmation of applicable conditions. A subsequent evidence-backed effectiveness review closes it. An implemented change cannot be cancelled to bypass this review.

Authority approval and notification default to required. The owner can document applicability and conditions before review; prior approval implies notification. A physical address change always requires written notification and at least fourteen days before implementation. Changing scope, proposal or Authority requirements reopens readiness. Returned/rejected decisions preserve immutable history and reopen readiness and the approval chain.

The register, pending approval, implemented and rejected/returned queues use the governed project source, with filtering and counts performed before pagination. Accepted changes awaiting implementation are not presented as implemented. Older mission histories retain their original interpretation; they are not retroactively given new implementation events.

The Historical records link retains access to the old read register. Its generic write routes remain blocked. Ownership options explicitly include non-auditors so executive and support personnel are not omitted by the audit-only default.

Forms select retained evidence by filename, link to the authoritative Document Control workspace, check short or blank entries, and send the loaded update timestamp to detect stale saves. Focus changes do not silently replace an open detail form. A deliberate reload action fetches the latest version. The active action appears before the readiness register; narrow screens render readiness rows as cards.

Document Control opens in the current authenticated tab. Unsaved assignments, gate reviews, decisions and delivery fields are retained in session storage scoped to actor, tenant, change and server update timestamp. Successful writes clear the old draft. A newer server version does not reuse the older draft. Empty queues show a compact state without a blank grid or pagination, and creation does not repeat the New/Refresh controls above the form.

## Verification

Database checks use temporary tables on PostgreSQL with an outer transaction that is always rolled back. No production change, approval, notification, implementation or closure record is created by these tests. Browser fixtures exercise controls separately from the authenticated live portal. Live navigation and empty states do not establish that a real business change has been approved.

Evidence checks resolve retained asset metadata and disposition and compare the captured checksum; file custody remains owned by Document Control. Review findings are human attestations, rather than automatic validation of the document's regulatory content.

Validation passed: 49 backend contract/input/settings checks, 11 PostgreSQL temporary-table checks, nine Chromium tests against the production build, targeted ESLint, and the production build's modal/type/chunk checks. The Chromium checks include returned workflow navigation, evidence selection, draft restoration after reload, history access, compact empty queues, and implementation followed by a separate effectiveness review.

The authenticated public Tailscale review checked all four queues and creation through the actual menu, inline field feedback and mobile layout, history access and a same-tab Document Control handoff without another login. No live business approval or change was created; the tenant's governed register contained zero projects. Live API checks returned HTTP 200 for the four queues and the non-auditor personnel list, which included an Accountable Executive.

Published frontend: `release-639283523200313715`, entry `/assets/index-diAOzbOd.js`. Local evidence and test logs are ignored under `.artifacts/change-approval-*` and `.artifacts/live-change-*-20261023.png`. The earlier live empty-grid capture is failure evidence; the subsequent published compact capture is the acceptance evidence.

The existing signed-in tab detected the new release and successfully reloaded from `index-GiiXVFFZ.js` to `index-diAOzbOd.js`. The final live empty queue measured approximately 197 px, with no horizontal overflow at 390 px. The planned frontend gateway restart briefly produced background HTTP 502 responses; after restart, readiness, the approval queue and notification reads returned 200, and the subsequent settled review recorded no HTTP/page failures.
