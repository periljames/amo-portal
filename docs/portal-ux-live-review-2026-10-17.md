# Portal UX review — 17 October 2026

## Scope and evidence

Live checks use the running portal at `http://127.0.0.1:5173`, the real API at port 8080, and a separate owner-authorised Safarilink verification account. Credentials are stored only in an ignored local runner artifact. Existing users' passwords were not changed. No personal regulated auditor privileges were granted. Tenant administration permits inspection; it does not make the account an assigned fieldwork auditor.

Backend source edits and further failing backend write attempts are deferred at the owner's request. A successful health check is not evidence that a business command or another device received an event.

| Surface | Live evidence | Remaining qualification |
| --- | --- | --- |
| Login | Desktop and 390px phone render; no page exceptions or HTTP 500 during navigation | Physical iOS/Android testing remains |
| Quality control room | Authenticated desktop and phone render without document overflow | No claim that every dashboard metric is correct |
| Audit Prepare | Existing preparation/readiness and controlled sources load with tenant access | Source rebuild failed; see backend queue below |
| Audit Fieldwork | Existing register renders; search/theme/disclosure components have browser coverage; phone page does not overflow | The existing audit still uses its legacy 236-row binding; this account correctly remains read-only |
| DMS Home | Real assigned document work loads; phone work item and action are visible; no horizontal document overflow | Approval, publication and retention actions are not exercised on operational documents |
| DMS Library | Authenticated phone library renders without document overflow | Reader/upload/revision workflows still need their own mobile journey checks |
| Realtime | Authenticated `/api/events` returns 200 and audit workspace reports `connected` | End-to-end business-event delivery, two-device edits and replay are not yet certified |

Screenshots and machine-readable reports are under `.artifacts/live-verification/` (ignored by Git). The reusable live browser checks are `frontend/tests/e2e/portal-ux-live.spec.ts` with `frontend/playwright.portal-ux-live.config.ts`. They use `E2E_LIVE_PORTAL_UX=1`, `E2E_BASE_URL`, `E2E_AMO_CODE`, `E2E_AMO_ADMIN_EMAIL` and `E2E_AMO_ADMIN_PASSWORD`; they do not need a backend restart or fixture seeding.

## Frontend upgrades implemented

1. **Reading hierarchy.** Canonical system font stack, 400 body / 500 labels / 600 headings, 15px desktop body and 16px phone body, relative-size labels and captions, 1.55 body leading and a 72-character prose measure token. Removed heavy 700–850 weights from the shared navigation and the audited QMS/DMS styles. The fieldwork panel has a contextual level-two heading instead of repeating the audit title as another level-one heading.
2. **Warmer themes.** Warm ivory/stone surfaces in light mode and solid warm charcoal surfaces in dark mode, using shared semantic tokens. Removed duplicate dark palette declarations from the older depth adapter so it no longer replaces the canonical palette. Operational status colours keep their meaning and text labels. DMS dark surfaces now follow those tokens rather than overriding them with hardcoded navy. DMS warning notices and secondary text consume semantic colours. DMS and offline-recovery primary buttons use the paired foreground token. Selectable accent swatches use shared palette tokens; teal/amber shades were adjusted for readable white button text.
3. **Navigation.** Administration groups collapse independently; the active group opens automatically. Larger labels, quieter weights, search, distinct active state and 44px phone controls improve scanning. Hidden navigation is `inert`; modal navigation makes the background workspace `inert`. Escape closes the drawer and restores focus. A stored desktop pin becomes a dismissible drawer below 901px without discarding the desktop preference. A missing saved width now uses the intended default instead of coercing `null` to zero and clamping it to the minimum.
4. **Phone header.** The assigned-work shortcut is available in the account menu while its duplicate header icon is hidden on narrow screens. Account/appearance and the theme/density/motion selectors have explicit accessible names. Header controls fit the tested 390px viewport. Menus stay within the viewport; the drawer respects device safe areas. Accent swatches have 44px targets. Navigation preference-storage failures no longer throw from the shared shell.
5. **DMS work cards.** Home retains a desktop table. At phone widths each work item keeps its task, document, status, due date and full-width action together. Column labels remain visible, column headers have scope, and the table has a caption. Users no longer have to scroll sideways to find their action.
6. **Action emphasis.** Start work is the DMS controller's primary header action. Add document and Open library are secondary actions; library remains primary for a reader who lacks controller actions. Form submission emphasis and business permissions remain intact.
7. **Motion.** Short opacity/position reveals and eased drawer/disclosure transitions communicate state. No scroll hijacking, parallax or looping decoration was introduced. Existing explicit and operating-system reduced-motion preferences continue to disable motion. Compact density does not shrink phone navigation targets below 44px.

## Typography evidence and limits

The decision is a practical default, not a claim that a particular font prevents eye strain or is statistically best for long shifts. Wallace and colleagues found substantial individual differences in reading speed across fonts; their interlude-reading study does not establish a universal long-session ergonomic winner. See the [author-hosted research paper](https://shaunwallace.org/files/Readability__TOCHI.pdf). Native fonts also avoid a font-network dependency for offline use.

Spacing, reflow and contrast are measurable acceptance criteria. [W3C visual-presentation guidance](https://www.w3.org/WAI/WCAG21/Understanding/visual-presentation) supports limiting long prose lines and increasing line spacing. The spacing/reflow work is not a declaration of full WCAG conformance. Warm colours follow the requested aesthetic; no medical benefit is claimed. Motion follows the principle of helping users understand changes, with reduced-motion support, as described in [Apple's motion guidance](https://developer.apple.com/design/human-interface-guidelines/motion).

## Remaining frontend UX work

This is a prioritised review queue, not a claim that unvisited workflows have passed.

| Priority | Upgrade needed | Acceptance evidence required |
| --- | --- | --- |
| P1 | Complete the phone journey through DMS library → reader → document details → permitted workflow action | 320/390/768px, long titles, PDF loading/failure, browser back and restored reading position; action reachable without horizontal page scrolling |
| P1 | Review audit evidence/detail drawers with the software keyboard open | Question context remains visible; attachment/action controls clear the keyboard and safe area; close restores the original row focus |
| P1 | Consolidate duplicated QMS stage actions, status chips and secondary launchers | One clear primary action per stage; secondary actions do not cover checklist content on phones; lifecycle controls keep authoritative disabled reasons |
| P1 | Verify offline feedback on dedicated disposable QMS/DMS records | Device-saved, pending, server-confirmed, conflict and failed states are visibly distinct; edits survive reload and sync exactly once in a production service-worker build |
| P1 | Verify text resizing across every necessary page | 200% browser text/zoom, user text-scale choices, long translated labels and user text-spacing overrides do not clip controls or hide actions |
| P1 | Extend table/card patterns beyond DMS Home | Prioritise library results, reviews, distribution/custody, findings and CAR work queues; keep comparison tables scrollable only where comparison needs columns; retain labels and keyboard semantics |
| P2 | Finish typography token migration across older module-specific CSS | Remove remaining tiny fixed labels, arbitrary heavy weights and hardcoded font stacks after inspecting each layout; no blanket weight or colour overrides |
| P2 | Consolidate overlapping style ownership | Review `qms-usability-enhancements`, text-scale adapters and older theme repair files; remove obsolete rules only after reference and computed-style checks |
| P2 | Review search and navigation discovery with operational users | Assigned work, current department and favourites are easy to find; collapse is reversible; keyboard focus order follows the visible UI; a search miss has useful feedback |
| P2 | Standardise skeletons, empty/error/retry states and live announcements | Stable page geometry, local retry, preserved drafts, no repeated screen-reader announcements or misleading healthy/saved claims |
| P2 | Measure mobile cold-start and interaction costs before further animation or asset additions | Profile LCP/INP, first useful data, route transitions and reconnect on a representative slower phone/network. The build reports a 984 KiB application entry, with PDF/grid engines excluded; that bundle check is not a measured user-perceived speed result |
| P2 | Check all accent/theme combinations and both density settings | Text 4.5:1 and meaningful graphical/control contrast; status meaning survives colour blindness; active/focus/disabled states are distinct |
| P2 | Physical device and long-session evaluation | Safari/iPhone, Android Chrome, tablet and keyboard checks; representative staff compare reading comfort, task accuracy and completion time over realistic sessions |

## Backend failures and integration queue — deliberately deferred

| Priority | Observed fact | Later investigation and exit criterion |
| --- | --- | --- |
| P0 | `POST /api/maintenance/safarilink/quality/audits/f231f732-d27b-4bbd-8b47-a2816ef931d5/checklist-bindings/rebuild-source` returned HTTP 500 during the live UI repair attempt. The response body was plain `Internal Server Error`, not JSON. No successful rebuild or preparation issue was observed. | Capture the correlated server traceback before editing. Trace the transaction, source/template/binding creation and preparation snapshot. Prove rollback on failure and a successful guarded rebuild to 172 rows, preserving old preparation/history and requiring issue of the new preparation. Do not infer the exception from the HTTP code. |
| P0 | Source review returned 200 with 236 existing imported rows, 172 parsed assessment rows, `can_rebuild=true`, `blocker=null`. | Recheck the live binding after the failure; do not mark the operational checklist repaired until its issued binding and rendered question count are both verified. |
| P0 | The earlier reported fieldwork-mutation 500 has not been reproduced by a valid assigned auditor during this pass. Tenant inspection access correctly does not grant fieldwork write authority. | Use a disposable governed audit and an eligible assigned auditor. Verify online save, offline durable queue, reload, reconnect, lost-response replay, stale-version conflict and independent device refresh. Never weaken assignment or approval guards to make a test pass. |
| P1 | The backend realtime switch was true while the frontend switch was absent, preventing browser event streams. The local frontend switch is now enabled; the development launcher has an inheritance regression check. | Confirm deployment build flags too. Deliver a real domain event between isolated authenticated devices, measure screen update latency, and verify reconnect/replay without unrelated module fan-out. A connected stream alone is insufficient. |
| P1 | Prepare reports unavailable Reliability ledgers. DMS reports one failed indexing record and governance/acknowledgement work. | Determine whether these are schema/module availability, job failures or actual retained business exceptions; preserve accurate local warnings. Do not clear or hide records to make the dashboard appear healthy. |
| P1 | One repeated-run login stayed on the sign-in page with the generic “Could not sign in. Try again.” message. Its HTTP failure cause was not captured. A subsequent live login returned 200 and entered Quality; liveness/readiness remained 200. | Capture the failing request, timing and correlation ID before assigning a cause. Do not label this as rate limiting or a database failure without evidence. The UX suite now signs in once and reuses that legitimate in-memory session for its isolated browser contexts. |

## Validation record

- Ten checklist/theme/realtime fixture browser cases passed after the shared typography/theme changes, including sampled light/dark text contrast, reduced motion and the actual 172-row source fixture.
- Three authenticated live browser checks passed: responsive pin/drawer/focus/touch behaviour, complete DMS phone work items, 320/390px layouts, cached Home navigation offline and offline theme changes. The live check measured primary-button text contrast at least 4.5:1 for all six accents in both themes and confirmed normal-weight DMS description text. These do not test hard reload with a production service worker or offline business writes. Offline Home retained its work cards and accurately warned that governance exceptions could not be refreshed.
- The four-route live phone sweep reported no page exceptions or HTTP 500 responses and no horizontal document overflow.
- Forty-one focused navigation/layout/realtime unit and contract tests passed. The CSS contract passed for 126 stylesheets. The production build passed; final build output is retained under `.artifacts/live-verification/final-build.log`.
- None of these results certifies all modules' offline writes or physical-device behaviour. The backend command failures above remain open.


The subsequent [checklist workspace revision](checklist-workspace-review-2026-10-17.md) implements the fieldwork rail/header/activity consolidation, inline question context, direct evidence capture and durable draft/completion recovery described in the follow-up review. It supersedes the corresponding pending layout entries above; backend failures remain open.
