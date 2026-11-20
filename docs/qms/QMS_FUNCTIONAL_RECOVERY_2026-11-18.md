# QMS functional recovery — 18 November 2026

## Verified starting state

Admin API login succeeded for Safarilink. The source audit read 50 existing
register views without HTTP failures or missing-table warnings. This did not
establish functional workflow coverage: Management Review had no dedicated
meeting lifecycle, My Quality Work's five views all selected notifications, and
the risk-matrix view selected `qms_settings` rather than risk assessments.

The main router short-circuited shallow canonical paths into a generic register.
Adding a specialist only to `QmsCanonicalPage` therefore did not repair list/new
routes. An automated browser flow reproduced this before route ownership was
corrected in `router.tsx` and the preload registry.

## Implemented workflow changes

- Permission-filtered page directory derived from the route registry, direct
  section-view links, keyboard navigation and searchable workflow vocabulary.
- Dedicated Management Review: draft, scheduling, conduct, inputs, minutes,
  decisions, approval, action assignment, completion evidence, verification,
  retained history, record download and closure gates. Concurrent edits use
  locked source rows and version checks. The calendar projects meeting and
  action dates and links back to the source workflow.
- Operational control forms use existing tenant-scoped QMS tables for process
  definitions, QMS scope, objectives, risks, treatment plans, opportunities,
  equipment, calibrations, certificates, out-of-tolerance events and external
  cases. Required fields, active owners, source relationships, stale versions,
  evidence-dependent closure and safe complete CSV exports are enforced.
- Calibration results update the latest equipment due date. Failed calibration
  and open out-of-tolerance events remove equipment from service. A passing
  calibration does not silently reactivate out-of-service equipment. Explicit
  return-to-service evidence is required. Completed calibration records cannot
  be overwritten. Open out-of-tolerance cases block reactivation even when a
  serviceability note is supplied. Future-dated completed calibrations are
  rejected before any record or equipment update is written.
- Risk matrix counts recorded open assessments. Risk levels are explicitly
  selected by the assessor, rather than invented from an unapproved threshold.
  Current distribution is identified as current data, not historical exposure.
- Source links for equipment, calibration, certificates, external commitments
  and review actions use the actual registered record surfaces.
- My Quality Work projects assignments, governed review/verification queues,
  overdue dates, completed records and personal watches from source records.
  Watch preferences do not change assignment or approval authority.
- The activity-history page displays actual actors, source events and retained
  before/after values. Management-review transition reasons are retained in
  visible history and meeting downloads.
- Findings analysis now has dedicated severity, process and monthly-event
  views. Process areas come only from current verified links to approved active
  controls; unmapped findings stay visible. Linked-CAR views use the server's
  bounded linked-record filter. New finding capture selects its source audit
  and opens governed Fieldwork instead of a generic record writer.
- The app-wide page directory remains available inside audit occurrence stages;
  the previous stage stylesheet explicitly hid it.
- The directory and dropdowns expose the Assurance control library, readiness,
  control evidence, intelligence reviews and the distinct Assurance Cases
  workspace. Finding creation uses its actual `qms.finding.create` permission,
  including authorized auditors, rather than an invented manage permission.
- Calibration Reports now shows current equipment/due-date gaps, open tolerance
  cases and retained completed results. Its CSV includes tenant totals and the
  filtered history, preserving zero values. Missing dates and unclassified
  legacy results do not become successful or current calibrations.

Generic writes are blocked for the governed review and control-register modules
so the old endpoints cannot bypass the new validation and concurrency rules.
No new production database tables or synthetic tenant business records were
created for validation.

## Evidence collected so far

- 35 focused backend tests passed, including lifecycle and control-register
  tests against SQLite and PostgreSQL, and the existing planner contracts.
- 12 assurance metrics / wiring contract tests passed.
- A subsequent 19-test SQLite/PostgreSQL run including Inbox assignments,
  overdue/completed filtering, watches, tenant boundaries and approval
  permissions passed.
- 69 frontend route, loader, navigation and planner tests passed.
- Production build passed TypeScript, modal-layer and route-chunk checks.
- Four production-browser tests passed: risk creation/editing/matrix/CSV,
  management-review creation/scheduling/download, read-only controls, and
  direct navigation / page search. Mobile screenshots were inspected; shared
  tab styles were then moved into the tab component's own stylesheet.

## Further verified results

- All 94 registered non-creation QMS views passed an authenticated Safarilink
  browser sweep with no page error alerts or failed authoritative requests.
  This established navigation and source-read coverage for that candidate;
  inspecting the results exposed duplicate Findings semantics, which prompted
  the separate Findings repair described above.
- The standard Quality frontend suite passed again: 24 files, 166 tests.
- Audit preparation/notice, closing-report governance, legacy mobile closeout,
  finding-to-CAR traceability and CAR control-loop browser regressions passed.
  The 236-question checklist write/evidence scenario also passed after isolating
  synthetic-session background requests and allowing time for its screenshots.
- Ten equipment/control-register tests passed against SQLite and PostgreSQL,
  including the new open-tolerance-case return-to-service gate. Seven review
  tests passed after retaining transition reasons.
- Six new finding-analysis tests across SQLite and PostgreSQL plus ten existing
  register tests passed. These cover real event dates, old findings closed in a
  later year, duplicate mapping edges, invalidation/expiry and tenant ownership.
- The combined final backend run passed 46 tests. The equipment/report suite
  passed 12 SQLite/PostgreSQL cases. The latest navigation suite passed 47 tests,
  and all 130 stylesheet contracts passed.
- Live Safarilink browser interactions reached new review and calibration forms,
  opened existing assigned source records and verified that classification
  drill-downs return the matching retained finding cohort. No business forms
  were submitted by those live checks.

Artifacts are retained under `.artifacts/`, including
`qms-live-browser-audit-20261118.json` and per-run test/build logs. Production
tenant reads were authenticated; workflow write fixtures use isolated SQLite
databases or connection-private PostgreSQL temporary tables.

The tenant-alias tab issue was corrected and verified with both the real
Safarilink login slug and trailing-slash entries. All 26 browser workflow checks
passed on the managed Shared release at port 5173. The expanded 106-destination
live sweep is in progress. A successful page load alone is not evidence
that every business lifecycle is complete or compliant. Existing overdue work
and unverified business evidence have not been fabricated or closed to improve
readiness scores.

## Running the verified release

Port 5173 serves an immutable copy of the verified production build through the
repository's Shared gateway. The previous development server was stopped after
its tests completed. Backend/API and ops gateway remain on 8080 and 8090 under
the managed runtime. Ownership and release paths are recorded in
`.artifacts/portal-runtime/backend.json` and `frontend.json`.

Stop all managed portal services with `scripts/Stop-Portal.ps1`. To publish later
frontend source changes, build the frontend, stop only the Frontend service, and
start it again with `scripts/Start-Portal.ps1 -Service Frontend -FrontendMode Shared`.
Rebuilding `dist` does not replace the running immutable release or invalidate
its in-flight asset requests.


## Live complaints and readability iteration (18 November, afternoon)

The user reported repeated complaint entry attempts and supplied the audit workspace screenshot. Native Chrome inspection of the actual Tailnet URL reproduced a database-unavailable register error, then recovered and showed the user's single retained Test Customer Complaint. The API log contains one completed 201 creation for that record; repeated client attempts cannot all be attributed to duplicate server writes.

Implemented in the existing views:
- Per-draft submission identifiers, transaction-scoped duplicate-create protection, immediate saved-record caching, double-submit suppression and tab-scoped draft retention by user and tenant endpoint.
- Customer-specific reference, category, issue/impact and containment fields. Known external-party suggestions and tenant-owned registered-provider selection; active owner selection remains mandatory.
- Issuer origin, finding level as issued, exact alternative classification, requirement reference, impact, containment and issuer deadline for external findings. Regulatory closure requires authority acceptance as well as resolution evidence.
- The existing provider findings view now uses a validated provider-linked editor with issued level and closure evidence. No additional pages were introduced.
- External findings appear separately at high operational priority in the existing assurance queue; overdue external findings escalate the queue urgency. The labels do not reinterpret an authority's official level.
- Audit scheduled dates collapse a single day to DD MON YYYY; differing start/end dates appear on separate lines. Table wrapping respects column definitions and no longer truncates generic register values at 130 characters. Shared Quality typography uses a readable body/label/table scale, with clearer dark-mode attention badges and provider panel padding.

VM diagnosis: PostgreSQL remained running with ample memory, but failed Snap applications repeatedly attempted startup. snap.nextcloud.apache.service alone had more than 6,400 restarts with 'timeout waiting for snap system profiles to get updated'. Temporarily stopped the eight Nextcloud Snap service units, their logrotate timer and the Prometheus Snap unit. No data or configuration files were deleted. VM CPU idle recovered from 0% during the startup activity to 53–72% in observed samples. These services remain paused; the underlying Snap installation still needs repair before restarting them. This is consistent with the observed connection timeouts, but does not prove every earlier retry had that cause.

Validation for this iteration uses compilation and direct live browser inspection, following the user's instruction to avoid more broad/ad hoc test runs. Earlier running jobs were allowed to finish: the 106-view navigation sweep passed and the combined backend run passed 48 cases. Those earlier checks do not substitute for visual verification of this iteration.

Additional live findings and corrections:
- After a restart, a burst of PostgreSQL connection timeouts recurred despite the Snap services being stopped. The circuit previously counted every concurrent request failure as a new recovery failure and repeatedly postponed the recovery deadline. Recovery backoff now advances only on an actual failed recovery probe; in-flight request failures cannot continually postpone it. This VM runtime uses a 15-second connection timeout.
- Controlled form schema/owner/provider authority is excluded from persisted and stale offline caches, including React Query persistence keys. This prevents an obsolete form definition appearing editable while the current server is unavailable.
- Direct Chrome inspection after deployment confirmed audit dates 10 OCT 2026, 19 OCT 2026 and 27 OCT 2026 with single-day collapse. The narrow-window inspection exposed a global no-wrap rule; Quality cells now override it and right-pinned action columns are unpinned below 700px.
- The user's existing Test Customer Complaint was updated once through the live browser: category Other, issue text copied verbatim from its existing description, retaining its title/customer/reference/owner/due date. One PUT returned 200; the live page showed Saved: Test Customer Complaint and retained history version 2. No additional complaint or finding records were manufactured.
- Production build and final TypeScript compilation passed. The final CSS/cache-policy bundle was built and published to managed Shared frontend release release-639306009973622603, owner 26972. Backend owner 26636 contains the backoff correction. Readiness returned ready/database true and online, with no recorded failure since that restart at the observed check.

Final visual observations: provider findings loaded its existing route and exposed the required registered-provider selector, issued finding level, deadline, requirement, impact, containment and verification fields. The final bundle was activated using the portal update prompt. At 640px native Chrome width, audit activity wrapped onto two lines, scheduled dates remained fully visible, and horizontal scrolling exposed Attention, Next action and deletion controls while retaining the audit identity column. The browser was returned to the desktop Customer complaints register with its single retained record. A 390px viewport was not verified. No claim is made that every QMS workflow was revalidated in this bounded iteration.

### Effectiveness follow-up ownership — floating control removed

Removed the effectiveness response host from `QualityEnhancementsHost` entirely. Existing Assurance cases (Assurance menu → Assurance cases) retain the single effectiveness planning/conclusion workflow. Follow-up response actions now render within that selected case's effectiveness section, using the parent's plans instead of fetching/selecting a separate case. There is no fixed launcher or overlay. The follow-up section is omitted when the case has no unsuccessful concluded plans or existing response obligations. Existing response APIs and closure obligations are preserved. Read-only/terminal cases cannot mutate responses. Owner choices load for all response types, and decision reasons are no longer prefilled with an assertion of completion.

The subsequent screenshot identified a second shared-shell launcher, `Create audit handoff`. Removed that mount as well. Audit handoff is now a collapsed action on the specific controlled-change detail and on each eligible Intelligence signal. Source identity is supplied by the owning record, with no global source selector or overlay; creation continues to use the existing Planner API. Permission checks and pending/success guards prevent duplicate creation. Live inspection also revealed that the preexisting effectiveness-response API router had never been included in canonical Quality composition (requests fell into the unknown-module handler); it is now registered before assurance-family route ordering.

Validation: the initial effectiveness integration passed TypeScript; the combined contextual-action release passed Vite production build (`.artifacts/qms-contextual-actions-build.log`). Python compilation and scoped diff whitespace checks passed. Live Chrome sign-in recovered after transient database errors. The existing effectiveness case `ID-U52C0SS5` loaded, and its effectiveness-response GET returned 200 after registration. Its existing conclusion is effective, so no unnecessary follow-up form is displayed. Change Control currently has zero governed projects, so no source-specific audit action was fabricated or submitted. Activated the final release via Reload portal; the live Control Room displayed Healthy and both global launcher labels were absent from accessibility state and the visible header. No business records were created or altered in this iteration. Runtime owners: frontend 10424, backend 26116.

### Tenant header logo restoration

The stored Safarilink asset is the original 420-pixel wordmark (`Safarilink-Logo-1200px-x-1200px-2 (No Tagline).png`), retained under the tenant's legacy `backend/uploads/amo_assets` directory. The shared-storage resolver rejected that path, and the logo endpoint returned 204, causing the initials fallback. Added a tenant-confined legacy materialization path with checksum verification when recorded; arbitrary filesystem paths remain rejected. Header logos now use a proportional rectangular slot (144×36 desktop, 100×32 phone) with `object-fit: contain`, no circular clipping, and a white backing for consistent contrast across themes. The existing source image is retained without bitmap alteration or upscaling.

## Vendor account workspace recovery — 19 November 2026

Implemented a shared server-owned vendor identifier generator for interactive QMS and Procurement creation. Existing vendor codes remain unchanged; imported records are not rewritten. QMS onboarding no longer requests a manual code and now captures organization email, telephone, website and registered address in the existing supplier master. Whitespace-only legal names are rejected. Procurement uses the same identifier policy while retaining its existing Finance vendor linkage.

Reorganized external-accounts/register into Accounts, Invite representative, Submissions & reviews, and Access history views, with URL-persisted navigation. Added account-state filtering, organization totals, provider-specific deep links, connected QMS/Procurement/Document Control/Maintenance navigation, keyboard-accessible provider links, full-width responsive layout, readable wrapping, and collapsible per-account controls. Decisions now require an actual reason, rather than a prefilled assertion. Saved mutations are distinguished from subsequent refresh failures, invitation fields clear after success, and busy guards prevent repeated submission.

Replaced raw object-scope JSON entry with saved-boundary checkboxes and a server-backed eligible-record search. The new manager-only grant scope-options endpoint resolves the grant within its tenant and provides provider-bound contracts, issued RFQs, sent purchase orders, and tenant audit assignments. Queries were checked against the deployed PostgreSQL schema. Contracted work remains Maintenance-managed. Existing document boundaries are preserved and can be narrowed. No invitations, access grants, supplier approvals or business records were created or changed during implementation.

Validation and live deployment: core frontend TypeScript passed (`.artifacts/vendor-workspace-final-types.log`); production builds passed, including the final dark-theme contrast correction (`.artifacts/vendor-workspace-contrast-build.log`). Backend Python compilation and scoped whitespace checks passed. Live Chrome verified Accounts, Invite representative, Submissions & reviews, Access history, the existing supplier selector, grouped account controls, and the provider registration form. The manager-only scope-options lookup returned 200 for the existing pending account; partner review and Document Control endpoints also returned 200. The final table header contrast was checked visually after activating the final release. No invitations or access decisions were submitted. Runtime readiness reported API/database/migrations/broker/workers healthy.

Deployment also exposed a full D: drive: the release launcher recursively copied historical chunks into each new release, and a failed frontend process was initially reported only as an owner PID. Run-PortalService now retains only files referenced by the previous build's Vite manifest; Start-Portal verifies the listening frontend with a 120-second startup allowance. Automatic review blocked recursive deletion of obsolete build output, so generated releases are being preserved by moving them into `C:/Users/Admin/AppData/Local/AMO-Portal-Release-Archive`, with two prior valid releases retained on D:. NTFS compression was also applied to the generated release cache. No source, uploaded tenant assets or database files were removed. About 5 GB had been recovered at final live verification; archive/compression jobs remain in progress. Final frontend owner 6288 serves release-639306539461908117; backend owner 24540.
