# CAR feedback and review verification — 27 October 2026

CAR communication reuses `quality_car_actions`. Review decisions append their
author, timestamp and reason; later decisions do not replace earlier history.
Existing activity defaults to internal visibility. Public invitation access can
read only shared entries for its own CAR and cannot select private visibility.

The record and control views expose the same retained conversation. Invitation
updates use a refresh-only event stream with a five-second read fallback. Staff
views also refresh from the authoritative database. Updates preserve in-progress
RCA and reply drafts. Closed CAR communication is read only; revoked or expired
invitations fail closed.

Messages and newly proposed corrective actions retain mutation receipts so a
retry after a lost acknowledgement returns the saved record. A confirmed action
save is kept visible even if the subsequent read fails. Returned individual
actions can be revised after narrative acceptance without unlocking approved RCA.
Independent implementation review and effectiveness requirements remain enforced.

The migration is `quality_car_feedback_261027`, following
`quality_car_rca_261022`. It adds visibility and author/mutation metadata to the
existing activity table. Downgrade refuses to discard shared communication.

Targeted backend verification includes tenant isolation, historical pagination,
private-note exclusion, immutable rejection/acceptance reasons, closed-state retry
receipts, action retry receipts and bounded tenant/CAR loading. Tenant scope,
CAR control and assignee reads avoid eagerly loading the tenant's entire roster
and asset graph.

Browser regression coverage includes initial invitation loading and edits made
while an earlier autosave is pending. The live acceptance specification uses
separate auditor and auditee contexts and explicitly marked synthetic records.
Checkpoint screenshots replace continuous video recording on the shared VM host.
It can resume an already submitted synthetic CAR with
`E2E_CAR_RESUME_SUBMITTED=1`; this does not bypass any review or closure gates.

## Observed results

- 64 targeted backend tests passed. Nine browser regression scenarios passed
  against the production frontend build with mocked API fixtures; those nine
  scenarios are not evidence of live database closeout.
- On the public deployment, a marked synthetic CAR completed the evidence-linked
  RCA, corrective-action proposal, evidence upload and submission screens.
  Deliberately losing a committed action's acknowledgement retained the form and
  allowed a retry. The retained submission and its shared history were visually
  inspected.
- At the user's request, a new marked case, `QA-CAR-LIVE-F6A59B`, was created in
  their tenant with their existing account assigned as lead auditor and a separate
  synthetic respondent. That case was submitted. The user's existing roles were
  not elevated. Their authenticated QMS interface was visually inspected.
- Live acceptance, rejection, rework, implementation verification, effectiveness
  and closure **are not confirmed**. Repeated PostgreSQL connection timeouts
  opened the database availability circuit and prevented the control page from
  loading reliably. Both public and local frontend attempts reproduced the
  problem. Direct login/control/assignee checks also succeeded between outages;
  those intermittent successes do not establish stability.
- A runtime Tailscale database-endpoint trial reached the same PostgreSQL instance
  but did not eliminate outages. The original endpoint was restored. The marked
  submitted case and previous isolated verification records remain available for
  resuming verification; no operational CAR was used for test approvals.

The full live acceptance specification deliberately still fails if it observes
server errors or cannot prove final closure. It must not be reported as passing
until the database connectivity problem is resolved and the remaining real
review steps succeed.
