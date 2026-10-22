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
