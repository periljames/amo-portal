# Rostering Cross-Module Scenario and Acceptance Matrix

Primary issue: #347

This matrix extends the normal happy-path tests. It is intentionally separated from concurrent production PRs so agents can implement isolated slices without duplicating ownership.

## Priority definitions

- **P0:** tenant isolation, unsafe duty, data loss, indefinite loading or unauthorised mutation.
- **P1:** operational workflow is blocked, misleading or materially incomplete.
- **P2:** usability, reporting depth, resilience or scale improvement.

## A. Canonical bases and stations

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| BAS-01 | P0 | AMO A requests or mutates a base belonging to AMO B by ID | 404/403 without disclosing the other tenant; no mutation or audit entry for the foreign record |
| BAS-02 | P0 | Create codes or aliases differing only by case/spacing | One canonical normalised value; duplicate returns 409 |
| BAS-03 | P1 | Enter an invalid timezone such as `Africa/Nairobii` | Form and API reject it and suggest a valid IANA timezone |
| BAS-04 | P0 | Deactivate a base with active/future deployments, published duty, open work, training, audits or inventory | Impact dialog lists dependencies; deactivation is blocked until reassigned or a controlled closure workflow is used |
| BAS-05 | P1 | Duplicate physical bases were imported under old codes | Admin merges them; all foreign keys move to the survivor and retired codes become aliases |
| BAS-06 | P1 | Rename a base code after historical rosters were published | Canonical references remain intact; audit/export history remains understandable; old code is retained as an alias |
| BAS-07 | P1 | Base temporarily closes for a date range | Effective-dated closure blocks new assignments in that window without permanently deactivating the base |
| BAS-08 | P2 | Base supports only line maintenance, training or workshop activity | Shared base capability metadata is consumed by related modules rather than hardcoded per module |

## B. Personnel placement and mobility

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| DEP-01 | P0 | Home base WIL and temporary MBA deployment overlap | Home base remains historical/permanent; MBA is effective only during the deployment window |
| DEP-02 | P0 | Two primary temporary/relief/training deployments overlap | Second mutation is rejected with the exact conflicting record and dates |
| DEP-03 | P0 | Deployment starts or ends on the rostered date | Boundary behaviour is inclusive and consistent in API, planner, exports and ICS |
| DEP-04 | P1 | User cancels a future deployment | Record is cancelled with reason; UI does not attempt an invalid `end today` before the start date |
| DEP-05 | P1 | Temporary/relief/training deployment has no end date | Reject by default or require a specifically authorised indefinite exception and warning |
| DEP-06 | P0 | Inactive, suspended, terminated or system user is selected | New deployment and productive roster assignment are rejected; history remains visible |
| DEP-07 | P1 | Person is eligible to work at several bases but deployed to only one | Eligibility and current placement remain separate concepts |
| DEP-08 | P0 | Overnight shift crosses a deployment boundary | Actual roster assignment base remains stable; default resolution uses a documented local-time rule |
| DEP-09 | P1 | Shift moves from WIL to MBA with insufficient travel/rest time | Configured travel buffer contributes to a warning or hard stop before publication |
| DEP-10 | P0 | Two administrators edit the same deployment | Stale revision is rejected and the second user receives a compare/reload choice |
| DEP-11 | P1 | Deployment is changed after a roster was published | Impact list identifies affected assignments and requires controlled amendment/revalidation |
| DEP-12 | P1 | Base placement is changed while the user has approved leave | Leave remains source-owned; placement history is retained; no duty is created |

## C. Permissions, privacy and audit

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| SEC-01 | P0 | Ordinary employee queries all personnel deployments | Only own permitted data is returned; tenant-wide movement data requires scoped permission |
| SEC-02 | P0 | Planner delegated to one base/department mutates another scope | 403 with the exact missing scope/capability |
| SEC-03 | P1 | Quality Manager needs assurance visibility but not HR movement control | View and audit permissions are distinct from deployment mutation permission |
| SEC-04 | P0 | Admin creates, edits, ends, cancels, merges or deactivates | Append-only audit captures actor, tenant, reason, before/after, timestamp and correlation ID |
| SEC-05 | P0 | Explicit deny conflicts with role-derived grant | Deny wins consistently in backend and frontend capability rendering |
| SEC-06 | P1 | User lacks a mutation permission | Control remains visible but disabled with a reason and access-management action where appropriate |

## D. Guided setup and contextual help

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| UX-01 | P1 | First successful Planner access | Commitment explanation appears once after hard prerequisites resolve |
| UX-02 | P1 | User presses Escape or closes the explanation without `Got it` | Dialog closes without falsely recording acknowledgement |
| UX-03 | P1 | User acknowledges on one device then opens another | Server acknowledgement prevents repeat display; local storage is only an offline fallback |
| UX-04 | P1 | Guidance content version increases | Updated guidance appears once again for that user and tenant |
| UX-05 | P0 | No bases, shifts or roster period | One actionable prerequisite dialog explains each missing item and links to exact setup subsection |
| UX-06 | P1 | User follows `?tab=shifts` or `?tab=periods` | Setup opens that subsection and preserves a return URL to Planner |
| UX-07 | P1 | Hard prerequisite has no meaningful read-only mode | No misleading `Continue read-only` button is shown |
| UX-08 | P1 | One prerequisite check fails by network error | Planner remains available; failed source has its own retry and diagnostic ID |
| UX-09 | P1 | Keyboard-only or screen-reader user operates dialogs | Focus is trapped/restored, background is inert and labels/actions are announced correctly |
| UX-10 | P2 | Guidance system is reused in another portal module | Stable topic/version contract works without module-specific local-storage code |

## E. Planner lifecycle and editing

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| PLN-01 | P0 | Commitments, findings or contracts API hangs | Grid and available controls render progressively; optional pane times out and can retry |
| PLN-02 | P1 | Create, edit, move and delete a draft assignment | Mutation succeeds, audit reason is captured and affected validation refreshes only as needed |
| PLN-03 | P0 | Published assignment is edited directly | Direct mutation is blocked; user is guided to controlled amendment workflow |
| PLN-04 | P1 | Bulk assign 100 staff with 5 conflicts | Non-atomic mode creates valid rows and reports indexed conflicts; atomic mode rolls back all |
| PLN-05 | P1 | Copy week includes overnight shifts and source commitments | Only permitted roster assignments copy; source-owned commitments are never duplicated |
| PLN-06 | P1 | Pattern spans DST transition in another customer timezone | Local start/end intent is preserved and actual duration is explicit |
| PLN-07 | P0 | Two planners modify the same draft assignment | Optimistic concurrency prevents silent overwrite and offers reload/compare |
| PLN-08 | P0 | Offline mutation syncs after server-side publication | Queue detects conflict; it does not alter the published roster silently |
| PLN-09 | P1 | Planner chooses a base different from effective deployment | Dialog offers to create the dated deployment or cancel; eligibility and travel rules are checked |
| PLN-10 | P1 | Tenant has 2,000 personnel and a four-week horizon | Search/pagination/virtualisation keep interaction responsive without loading all users |
| PLN-11 | P1 | Licence/training expires during an overnight assignment | Validation considers the entire assignment interval, not only its start date |
| PLN-12 | P1 | Published roster is amended | Change set, approval, notifications and employee re-acknowledgement are recorded |

## F. Cross-module source-of-truth scenarios

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| XMOD-01 | P0 | Leave is approved after duty was published | Conflict appears immediately; planner can replace/amend but cannot edit the leave record in Rostering |
| XMOD-02 | P1 | Training event at another base is scheduled | Commitment shows exact time/location; authorised user may create a matching deployment without duplicating training |
| XMOD-03 | P1 | Quality audit assignment overlaps duty | Commitment identifies the audit and links to Quality for rescheduling |
| XMOD-04 | P0 | Employment contract ends mid-roster period | Productive duty after expiry is blocked; earlier valid duty remains |
| XMOD-05 | P0 | User is suspended or deactivated | Eligibility and open draft assignments refresh; publication cannot include the user |
| XMOD-06 | P1 | Work order changes base or planned dates | Capacity, assignment links, blockers and Gantt forecast recalculate without duplicate task records |
| XMOD-07 | P1 | Attendance is captured at a different base from rostered duty | Mismatch is flagged for supervisor review; roster history is not rewritten |
| XMOD-08 | P1 | Stores or Production imports a legacy base alias | Alias resolves to the canonical base ID or the import is quarantined for mapping |
| XMOD-09 | P1 | Training/Quality source is unavailable | Existing cached commitments display with stale timestamp; planner core remains usable |
| XMOD-10 | P1 | Source record is corrected or removed | Projection and findings reconcile idempotently without orphan duplicates |

## G. Compliance and overrides

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| CMP-01 | P0 | Rule has no controlled source citation | It cannot be represented as a KCAR statutory hard stop |
| CMP-02 | P1 | Approved MoPM rule changes effective date while a draft exists | Draft is marked stale and revalidation identifies affected assignments |
| CMP-03 | P0 | Non-overridable hard stop remains open | Draft may be repaired, but approval/publication is blocked |
| CMP-04 | P0 | User requests and approves their own override | Separation-of-duties rule rejects it |
| CMP-05 | P1 | Warning is overridden | Reason, evidence, approver, expiry and affected assignment are retained |
| CMP-06 | P1 | Training/licence source is corrected | Finding can be revalidated and resolved without deleting evidence of the original result |
| CMP-07 | P1 | Coverage is valid generally but not for aircraft type/base/task | Scope-aware finding identifies the precise missing authorisation |

## H. Operations, progress and reports

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| OPS-01 | P1 | Supervisor opens Operations with hundreds of work orders | Lightweight collapsed list loads first; no Gantt task graph is fetched yet |
| OPS-02 | P1 | One work order is expanded | Only that hierarchy/Gantt is lazy-loaded with planned/actual bars and dependencies |
| OPS-03 | P1 | Production records task progress | Consumed/remaining hours and forecast update with freshness timestamp |
| OPS-04 | P1 | Work has missing estimates | It is visible and excluded transparently from false capacity precision |
| OPS-05 | P1 | Capacity is positive overall but certifying coverage is missing | Workspace shows the coverage blocker rather than a misleading green capacity total |
| OPS-06 | P1 | Critical task slips | Critical path, forecast finish and affected aircraft ground time update |
| OPS-07 | P1 | Supervisor reallocates from the Gantt | Action opens controlled roster/task workflow; it does not mutate source records invisibly |
| OPS-08 | P2 | Export is generated during live updates | Export states data-as-of timestamp, filters and source freshness |

## I. Reliability, performance and accessibility

| ID | Priority | Scenario | Expected result |
|---|---|---|---|
| NFR-01 | P0 | Synthetic 2G cold Planner load | Useful shell/grid appears within the defined budget; optional sources do not serialize startup |
| NFR-02 | P0 | API request never settles | Client timeout, abort and retry prevent an indefinite spinner |
| NFR-03 | P1 | Browser goes offline after initial load | Cached roster remains readable; permitted draft mutations queue with visible sync status |
| NFR-04 | P0 | Offline queue replays twice | Idempotency prevents duplicate assignments/deployments |
| NFR-05 | P1 | 320 px mobile, tablet, 1080p and ultrawide | Core actions remain reachable; no hidden horizontal action rail or unreadable grid |
| NFR-06 | P1 | Reduced-motion and keyboard navigation | All interactions work without motion and with visible focus |
| NFR-07 | P1 | One tab/data source fails | Other tabs and sources continue; errors are isolated and actionable |
| NFR-08 | P1 | Cache contains another tenant's prior context | Tenant/user keys prevent stale cross-tenant display |

## Immediate audit findings for the first implementation slice

These items should be resolved in PR #349 or explicitly assigned to the next stacked PR:

1. Setup links include `?tab=shifts` and `?tab=periods`; the Setup component must consume those query parameters.
2. Contextual-help acknowledgement is currently local-storage only and backdrop/Escape dismissal records the topic as seen.
3. The prerequisite dialog always offers read-only continuation, including when no useful read-only workflow exists.
4. Operating Structure loads bases, up to 250 people and all deployments in one `Promise.all`; one failure blanks the whole workspace and larger tenants are truncated.
5. Deployment mutation uses hard-coded roles rather than scoped capability grants.
6. Tenant-wide deployment listing requires an explicit view permission; ordinary users must not enumerate personnel movement.
7. User deployment validation must reject inactive/suspended/terminated users.
8. `End today` is invalid for a future deployment and ambiguous for an inclusive current-day end.
9. Open-ended temporary/relief/training deployments need controlled handling.
10. Base deactivation currently lacks dependency impact analysis, audit reason and concurrency protection.
11. The first implementation slice does not yet apply effective base resolution to roster assignment defaults; this remains a required follow-on.

## Execution layers

- **Backend unit tests:** date overlap, precedence, permission, tenant isolation, state revision and rule behaviour.
- **PostgreSQL integration tests:** constraints, concurrent writes, migrations, aliases and merge/deactivation impact.
- **Frontend component tests:** dialog acknowledgement, deep links, error isolation and permission explanations.
- **Authenticated Playwright:** real role-based clicks/mutations across Admin, Planner, Supervisor, Quality and Employee accounts.
- **Synthetic network tests:** cold/warm 2G, hanging/failed source, offline queue and recovery.
- **Cross-module contract tests:** Workforce, Training, Quality, Maintenance, Production, Stores and notifications.
