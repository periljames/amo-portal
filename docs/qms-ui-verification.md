QMS audit UI verification
=========================

The audit workspace uses the portal's font, spacing, surface, focus, motion and semantic colour tokens. Light mode uses warm ivory/stone surfaces with the portal blue accent; dark mode uses warm charcoal with its gold accent. Green indicates satisfactory assessments, amber indicates incomplete/pending work and red indicates adverse responses. Labels, selection controls and sync messages accompany these colours.

Desktop retains a source-ordered assessment table. Phones keep each question, response choices, remarks and evidence action together in a vertical layout. Themes do not replace form state. Native disclosures support keyboard activation; reduced-motion preferences disable entrance animation and smooth scrolling. Theme controls use Lucide icons and synchronize preferences between open screens/tabs. Blocked preference storage does not prevent changing the current theme.

Browser checks use the production components and full portal stylesheet. They verify light/dark/system switching, persistence, cross-tab theme updates, preserved drafts, sampled text contrast of at least 4.5:1, matching font families, 44px touch controls, native disclosure toggling, reduced motion, section navigation, search, read-only controls and all 172 assessment rows from the local controlled Word upload.

Realtime verification uses the actual QualityDataFreshnessCoordinator, React Query and API response cache against a controlled HTTP fixture. It verifies that events replace cached answers, twelve rapid events produce one refresh, another audit and fleet stay untouched, reconnect refreshes current data, and replay resets refresh the active audit. DMS event routing tests cover dependent QMS document selectors/readiness without replacing frozen fieldwork rows.

Incoming audit events are grouped over 250ms. Local outbox/evidence changes update through storage notifications, with a two-second local polling fallback. Team presence refreshes every 15 seconds. When the realtime stream is unavailable, a visible online fieldwork page checks for changes every 15 seconds; the healthy-stream safety refresh remains two minutes. Hidden/offline pages do not run this network fallback.

Live retry on 2026-10-17: the API at 127.0.0.1:8080 and frontend proxy at 127.0.0.1:5173 both returned 200 for /livez and /readyz. Readiness reported the database online, migrations ready, broker connected, no consecutive database failures and a valid connection budget. Anonymous /auth/me returned the expected 401 through both addresses. The actual /maintenance/safarilink/login page rendered in desktop and 390px mobile Chromium viewports with no page exceptions or HTTP 500 responses during navigation. Its mobile document did not overflow horizontally and used the shared portal font family. Screenshots are saved under frontend/test-results/live-safarilink-login*.png.

Validation completed: the frontend production build, 59 focused unit/contract tests and 10 checklist/theme/realtime browser tests passed. The browser realtime tests use controlled HTTP responses; they are separate from the live health and login checks above.

Authenticated checks subsequently used a dedicated owner-authorised verification account. Prepare, Fieldwork, DMS Home and the library rendered against the real API. Three live browser checks passed for responsive navigation, complete DMS phone work items, cached offline navigation and offline theme changes; all six accents met 4.5:1 primary-button text contrast in light and dark. The browser realtime flag had been absent despite the backend flag being enabled; the local setting was corrected and authenticated /api/events returned 200 with a connected audit workspace. The source-rebuild command returned 500 and the operational 236-row binding has not been confirmed repaired. See the [detailed live UX review and deferred failure queue](portal-ux-live-review-2026-10-17.md).

Physical-device Safari behaviour, domain-event delivery between independent devices and all offline business writes remain unverified. Broker readiness or a connected stream alone is not evidence of those outcomes.


The subsequent [checklist workspace review](checklist-workspace-review-2026-10-17.md) records the compact fieldwork layout, direct camera/upload controls, encrypted draft/completion recovery, live mobile/offline checks and remaining backend contracts.
