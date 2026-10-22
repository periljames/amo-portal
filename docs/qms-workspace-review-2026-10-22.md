# QMS workspace and data-entry review — 22 October 2026

## Review findings and changes

The route inventory, dispatchers, shared register, tenant shell, Quality context bar, administrator activation, and control-page forms were reviewed together. A successful route load alone is not evidence that a business workflow is correct.

| Area | Finding | Result |
| --- | --- | --- |
| QMS navigation | Tenant administration, other departments, personal tools and Quality controls were combined in one drawer. | The active QMS app has its own grouped navigation, including for AMO administrators. Other department and administration trees are not mixed into QMS. |
| Control navigation | The workspace bar emphasized six broad workspaces while controls required searching the drawer. Its sticky layer could cover page tools. | A visible Controls & Settings menu provides permitted control destinations. The bar wraps at narrow widths; measured scroll padding keeps focused fields below it. Competing sticky module tabs are removed. Shared registers expose their views directly. |
| Settings | Canonical dispatch treated configuration as a record table, with generic status and search controls. | A specialist settings workspace owns overview, workflows, numbering, notifications and retention. Existing scalar policy values have typed controls; structured policy arrays retain source ownership. Unconfigured policies are not presented as fabricated settings. |
| Administrative work | Standing administrators were permanently shown as active; delegates had a fixed 30-minute activation. | Both explicitly activate Admin View from their profile for four hours (default), until midnight in the AMO timezone, 24 hours or one week. The server enforces login-scoped activation and grant expiry. Turning off the view preserves the appointment. |
| Exit from administration | An administrator without an operational department could be routed straight back to administration after deactivation. | The operational fallback opens Quality. |
| Reply addresses | A text area required users to understand mailbox delimiters. | Separate email fields, + Add email and Remove controls; syntax, incomplete entries and case-insensitive duplicates are checked before submission. The existing API serialization is retained. |
| Provider entry | Code/name constraints were delayed until server submission. | Provider code and legal-name inputs use the backend's minimum/maximum lengths. Email fields retain email semantics. |
| Agreement metadata | Legal entities and sites were entered as newline/comma lists. | Add/remove item controls retain the existing wire format. |
| Provider qualification | Users entered an evaluation template UUID, questionnaire JSON, manual-reference delimiters and technical-scope JSON. | Named template selector, structured questions and technical-scope fields, and individual manual-reference controls. Existing opaque identifiers and additional row properties are preserved. |
| Qualification routing | The visible Qualification & Surveillance provider tab was absent from the outer router's allowed record tails. | The tail is registered and covered by route and browser regressions. |
| Form feedback | Many forms waited for submission to expose basic entry mistakes. | One QMS-wide controller gives inline HTML-constraint feedback on leaving fields, updates it while correcting entries, checks whitespace-only required values and prevents invalid native form submission. Prose uses browser spell checking; emails and explicitly marked codes do not. Values are not silently autocorrected. |
| Register presentation | Pages exposed transport language and serialized objects rather than explaining the work. | Module-specific purpose text, direct view links, responsive toolbars and readable list values; complex record details are opened in their owner. |

## Page inventory and ownership

All registered modules were checked against the frontend registry and dispatcher. The shared register views are covered by the browser sweep; specialist business actions retain their own contracts and permissions.

| Module | Intended surface / review |
| --- | --- |
| My Quality Work | Assignment queue and personal tasks; shared register and source links. |
| Calendar | Planner specialist; preserved rather than replaced by the generic register. |
| Audits & inspections | Assurance programme, register and occurrence stages; specialist ownership retained. |
| Findings | Assurance-owned findings and corrective-action links. |
| CAR / CAPA | Specialist response, review, evidence and effectiveness workflows. |
| Risk & opportunities | Register, matrix, opportunities, treatment and trend views. |
| Change control | Proposed, pending, implemented and rejected work; creation remains governed by its source. |
| System & processes | Process, scope, objective, risk and opportunity views. |
| Controlled documents | Library, change, approval, distribution and obsolete views; document readers retain specialist ownership. |
| External Providers | Provider register, agreements, qualification, evidence and oversight; entry constraints and linked controls reviewed. |
| Vendor Accounts & Access | Separate account authority, invitations and submission reviews within QMS. |
| Equipment & calibration | Register, deadlines, certificates, history and out-of-tolerance views. |
| External interface | Regulator findings, customer feedback, correspondence, commitments and responses. |
| Management review | Review meetings and action views. |
| Reports & analytics | Executive, audit, training, finding and export views; CAR performance retains its report owner. |
| Evidence Vault | Bounded search and retained evidence; record viewers and download ownership preserved. |
| Mail identity | Existing sender and delivery settings with explicit Reply-To list entry. |
| Settings | Dedicated configuration owner; excluded from generic register dispatch. |
| AeroDoc | Optional specialist document tools; not enabled merely by adding the new menu. |

## Verification scope

Backend checks cover administrator activation, deactivation, concurrent-login isolation, grant limits, standing appointment retention, timezone/DST midnight behavior and tenant/platform boundaries. Frontend checks cover route metadata, navigation scope, preload selection, activation serialization and address validation.

Browser verification uses isolated API fixtures for settings edits and administrator UI, so it does not create tenant records, send email or activate a real user's administrator session. The register sweep verifies rendering/navigation for every shared-register view; it does not certify domain approvals, real mail delivery or every specialist lifecycle. Production build checks and public readiness are checked separately before release.

The automated register sweep covers 47 views. Additional browser checks cover settings save scope, individual email validation and duplicate detection, administrator activation/deactivation, mobile geometry, dark appearance, qualification entry and existing vendor entry points. Screenshots and logs are in the ignored `.artifacts/qms-*` files.

Release verification completed: 50 backend tests, 88 frontend unit/contract tests, and 10 Chromium tests passed, including the 47-view sweep. The production build, modal-layer and heavy-route checks passed; the new shared form/settings components passed targeted ESLint. The managed frontend and backend were restarted together. Live API/database and operations readiness passed, the live OpenAPI schema exposes all four activation periods with `FOUR_HOURS` as default, and public HTML matches `/assets/index-DMJkLv2M.js` from the tested build. A pinned public Funnel ingress returned readiness HTTP 200 in approximately 1.5 seconds. Preview servers were stopped after verification. Evidence: `.artifacts/qms-ux-release-build.log`, `.artifacts/qms-ux-final-browser.log`, `.artifacts/qms-ux-unit-tests-final.log`, `.artifacts/qms-admin-view-tests.log`, and `.artifacts/qms-ux-live-release.json`.

Server validation and existing approval rules remain authoritative. Browser spell checking depends on the user's installed dictionaries; it is not a server spelling service or automatic correction of legal names, codes or evidence.

## Live follow-up and MOPM alignment

The later authenticated review used the real `AMO_ADMIN` account with its standing tenant-administrator appointment and Quality department context. It exposed two production errors hidden by the isolated fixtures: settings queried columns absent from the canonical `payload` schema, and supplier search passed a SQL bind named `query` into a helper already using that argument name. Both errors are corrected. Settings storage now supports canonical and legacy layouts, partial updates preserve unrelated groups, and supplier selection retains tenant filtering and bounded pagination.

Manual role gates in provider accounts, qualification, document review, contracted maintenance and Procurement now use the existing tenant-administrator authority helper. Frontend capabilities use the matching administrator policy. Administrators retain tenant restrictions, evidence requirements, separation of duties and provider/staff identity boundaries. This corrects role inheritance without fabricating technical qualifications or signed releases.

The navigation now uses one compact Work / Assurance / Controls & settings / Reports dropdown bar with actual page destinations. The redundant assurance rail, register view strips, Settings tab strip and CAR queue strip are removed. The QMS drawer is at least 360 px on desktop and clamps to narrow screens. Live captures confirmed a 44 px menu bar and a readable 360 px drawer after its transition completed. Query workspace highlighting now requires the selected query on the exact workspace page; Missions no longer appears active on Settings. The service worker uses version 14 and prefers the refreshed canonical shell over stale route-specific HTML.

MOPM functional and retention requirements, source fingerprint, regulation reference and coverage boundaries are in [mopm-portal-alignment-2026-10-22.md](mopm-portal-alignment-2026-10-22.md). This adds record/event-based retention, protected tenant extensions, separate audit-package safeguards, annual provider policy limits, contracted scope/Authority-access verification, and core duty/rest floors.

The expanded backend suite passed 106 checks. The frontend suite passed 61 checks, with the final retention-preview test bringing the covered total to 62. Targeted ESLint and the production modal/heavy-route checks passed. Browser cases cover 13 scenarios, including a 47-view register sweep. During the follow-up run an exact field selector stopped matching after inline validation changed its accessible name; this was corrected to retain the named input. The cold administrator case was rerun with an explicit workspace-loading allowance. The final register sweep follows the actual dropdown links and checks the destination URL, visible QMS content and navigation for all 47 views. Earlier repeated full-page reload sweeps exceeded their aggregate time limit during compilation; individual page rendering did not fail. Final run results and release evidence are appended below.

On the live authenticated site, readiness, settings, supplier search, provider-document retention policy and Document Control retention policy all returned HTTP 200. All three policy surfaces exposed the same version and 14 record classes. An attempted two-year maintenance-record extension returned HTTP 422 for the administrator; a before/after read confirmed settings were unchanged. These checks did not create a supplier, send an invitation, approve work or dispose of a business record.


Final release verification: the 13 browser scenarios passed across the completed main run and targeted reruns, including the 47-view menu sweep. The final TypeScript build check exited 0, targeted ESLint passed, and the production release passed modal/heavy-route checks. Public and live browser HTML both use `/assets/index-0lqxucK8.js`; the public service worker is version 14. The managed frontend release is `release-639282977969734590`.

Live visual captures show the 14-class retention configuration on desktop and mobile, inline rejection of a below-floor value with Save disabled, administrator invitation/account controls, the page dropdown and the 360 px drawer. The mobile main area measured 360 px wide with a 360 px scroll width. The live account's document permissions returned `quality_manager`, `quality_reviewer` and `document_controller` all true; the provider page had no alerts or failed HTTP responses. The final drawer highlights Retention and leaves Work collapsed. Public API and operations readiness returned HTTP 200 after publishing. Evidence files include `.artifacts/live-mopm-retention-desktop.png`, `.artifacts/live-mopm-floor-validation.png`, `.artifacts/live-mopm-retention-mobile.png`, `.artifacts/live-qms-admin-provider-access-verified.png`, `.artifacts/live-qms-page-menu-final.png`, `.artifacts/live-qms-drawer-final.png`, `.artifacts/mopm-register-menu-sweep.log`, `.artifacts/mopm-browser-resolved-cases.log`, and `.artifacts/mopm-publish-backend-verified.log`.

The older automated browser tab stalled during the service-worker update/reload. The published interface was subsequently verified in a newly opened headed browser with a normal authenticated login. This does not establish seamless migration for every already-open cached tab; a hard refresh or reopening the portal loads the current release. No production tenant configuration was changed by the visual draft checks.
