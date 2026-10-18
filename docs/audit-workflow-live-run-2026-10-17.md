# Audit workflow validation on 17 October 2026

This run uses the portal's rendered frontend. Audit records were not seeded, created through a script calling APIs, or edited in the database. Browser automation operates visible form controls. Backend source files remain unchanged.

## Test occurrence

- Reference: **QAR/MO/26/006**.
- Audit ID: `ad60605b-436c-4c40-b9bd-86d50979d782`.
- Title: WORKFLOW VALIDATION — SL-QMS-29 REV 01 — simulated audit.
- Source: one-off audit; the annual-programme invitation was declined through **Keep as one-off**.
- Lead auditor: James Muisyo. Auditee: Elvin Kinanga.
- Schedule selected by the creation form: 19 October 2026, 09:00–17:00.
- All randomized answers and finding scenarios explicitly identify themselves as synthetic workflow test data. They are not actual inspection results.
- Initial preparation used the existing verification account. Fieldwork uses James's actual frontend sign-in, authorized by the user. No impersonation or permission changes were used.

## Verified outcomes

| Stage | Observed result |
| --- | --- |
| Create standalone audit | Created and appeared in the audit register as One-off, with James as lead and Elvin as auditee. |
| Upload supplied Word file | Original server parser returned 172 candidates, including cover-sheet labels and incomplete sections. |
| Corrected frontend Word extraction | 189 numbered source questions. Every question's reference and normalized wording matched an independent read of the supplied Word tables; zero mismatches. Eleven main sections, with workshop subsections retained as fourteen selectable groups. |
| Source response scheme | YES / NO / N/A preserved, without adding invented source columns. |
| Bind checklist | Created and bound as `AUD-EF2722E0CCFE`, revision 1. Source filename and SHA-256 retained. The supplied document was not falsely sent for a new DMS approval or marked as an existing DMS record. |
| Issue preparation | Issued. A later frontend visit showed 100% readiness and the Open Fieldwork action. |
| Meetings | Opening and closing meetings saved through Setup's On site action. |
| Notice | `QAR/MO/26/006/N01` generated. Both downloaded PDF pages visually inspected. |
| Email delivery | Frontend Send notice and email returned **0 of 2 sent; 2 failed**. Notice remained GENERATED and Not delivered. Receipt of email is not confirmed. |
| Assigned auditor session | James signed in through the normal login form. Fieldwork controls became editable. Temporary local sign-in data was removed after use. |
| Critical finding | Submitted through question 1.1's NO response. `POST .../checklist-items/102a1cb0-7b83-405e-af2b-ae5d9d19de59/fieldwork-findings` returned **500**. The form retained its content and showed the failure. No finding or CAR is claimed as created. |
| Major and minor findings | Submitted through question details' Raise finding action for 5.7 (Level 2) and 8.4 (Level 3). Both finding mutations returned **500**. |
| Observation classification | The same classification dropdown contains **Level 4 · Observation**. A Level 4 draft for question 2.6 was retained; submission is unavailable under the current source-response contract, and the frontend explains that limitation without altering the approved source columns. |
| Ordinary checklist save | Question 1.2 returned HTTP 200 with a committed version, YES response and James's actor identity. Response survived reload. |
| Immediate response feedback | Initial response displayed stale state until reload. Frontend now applies committed mutation receipts immediately and rejects older row versions during reconciliation; the next save displayed immediately. |
| Finding draft retention | Failed critical finding parked using Save draft & continue; its Question 1.1 draft action survived a page reload. |

The randomized execution-order run finished with **186 / 186 ordinary questions saved**, each backed by a successful mutation receipt and explicit assessment fields. The remaining source questions **1.1, 5.7 and 8.4** are reserved for the failed Critical, Major and Minor finding submissions. The 189-question audit is therefore not complete. Ordinary answers use explicitly labelled synthetic YES scenarios; this is not a real compliance assessment or random evidence of compliance. The ignored `.artifacts/audit-workflow-run/checklist-progress.json` and `workflow-responses.json` files retain references, committed versions and mutation IDs.

## Frontend repairs in this run

- Word table extraction runs locally, using the existing lazy-loaded Word dependency. Only numbered question rows beneath explicit assessment headers become questions. Cover metadata, remarks, and workshop headings are excluded from question counts. Paragraph breaks, spaced references, source headings and answer meanings are preserved.
- Structured workflow failures display their message instead of raw JSON.
- Preparation reconciliation cancels older readiness/revision reads before refreshing after writes.
- Committed checklist receipts update the table immediately. Older reads cannot erase a newer committed row; fresh execution reads bypass the generic response cache.
- Required remarks no longer block entry into the finding form. The form includes the question, remarks, classification and objective evidence together.
- Finding failures appear inside the active dialog. Local and durably queued finding drafts release their temporary edit state correctly after acceptance/queueing.
- Multiple unfinished finding drafts can be parked independently and reopened after reload. They remain drafts, and prevent a false completion claim.
- The classification dropdown includes Critical, Major, Minor and Observation together. Question details provide a direct Raise finding action.
- Large checklist rows retain stable renders while another question's remarks/assessment change. Ordinary saves reconcile their committed row without waiting for unrelated findings, bindings, external-draft and lifecycle reads.
- Committed row receipts are retained in the encrypted device journal, so an older downloaded package cannot erase an acknowledged answer after an offline reload.
- Fieldwork's permission/readiness explanation is visible above the checklist, with a direct team or preparation link, instead of hidden in the activity menu.
- Failed email delivery uses warning/error feedback rather than a success checkmark; the send result can show each recipient's delivery status.

## Backend work deferred

1. **Finding creation 500:** reproduce using the retained test occurrence, question, authenticated actor and frontend payload. Obtain the server exception before changing code. Verify transaction rollback and absence of an existing finding/CAR before retrying. Ordinary checklist updates succeed, so this is not a blanket portal outage.
2. **Notice email dispatch:** the send action reached the workflow but reported two failed deliveries. A frontend retry as James confirmed both resolved recipients and returned the provider error `Invalid to field` (email or display-name/email format required). Both dispatch items remained FAILED, with no message ID. This confirms a delivery-path defect; it does not prove which provider adapter/configuration line caused it. Do not claim mailbox receipt based on notice generation.
3. **Word parser fidelity:** replace the 172-candidate output with source-aware table handling. The supplied document independently contains 189 numbered questions; cover metadata and spaced header cells exposed the defects.
4. **Level 4 with a YES/NO/N/A checklist:** source inspection confirms the atomic finding endpoint requires an OBSERVATION canonical answer for Level 4, while the source response validator rejects values absent from the frozen response scheme. A separate observation must be supported without falsifying the approved checklist's answer columns. This contract limitation has not been worked around by inventing an extra response or using a legacy mutation endpoint.

## Checklist interpretation to retain in the follow-up review

Source labels and question wording are reproduced correctly; this does not independently certify every answer's compliance meaning. For example, question 2.4 asks whether designated auditors are involved in day-to-day work in the audited area. A blanket YES = compliant mapping cannot establish independence for that question. The imported per-question meanings remain editable during preparation. The current test deliberately uses synthetic scenarios; its randomized answers must not be reused as a real assessment or evidence that the organization meets those requirements. The answer-to-finding workflow should support independent auditor judgment, including observations on an otherwise satisfactory item.

The run must not be described as complete at CAR handoff until findings/CAR creation and the auditee's actionable frontend state have actually been verified.

## Evidence and checks

Private runtime evidence is in `.artifacts/audit-workflow-run/`: source table HTML, the 189-page-control draft review, notice PDF and page images, finding failure screenshot, and actual frontend-triggered responses. Credentials are excluded from these reports and artifacts.

Focused import, networking, cache and receipt tests pass. The latest production build passed TypeScript, the 49-modal check and the heavy-route dependency check. Vite still reports large chunks; this is not evidence of acceptable load speed on a slow connection.

### Continued verification

- Before the interrupted browser session ended, 111 ordinary question saves had committed receipts. The restored frontend independently displayed **111 / 189**, confirming these answers persisted on the server. This is an intermediate count, not audit completion.
- An independently signed-in browser context at a 390-pixel viewport received a checklist progress change from **56 to 57 without reloading**, with the event stream connected. This verifies the observed cross-session update on one computer; physical cross-device behavior has not been certified.
- The focused realtime, committed-receipt and encrypted-journal recheck passed **14 tests**. The journal test retains unsent remarks, finding drafts and a completion request beyond a day; a storage-failure test protects the last successfully committed journal. These automated checks do not substitute for live offline replay.
- The normal production frontend is available locally on port 4173 against the existing backend. Its service worker was observed active and controlling the page. Development port 5173 disables that worker, so a development-only session cannot establish offline application-shell availability.
- The original automated browser session closed unexpectedly. Its in-memory browser profile is not evidence of durable browser-restart retention. Continued checks use a local persistent browser profile, with normal frontend sign-in and no copied authentication state.

No backend files were changed or backend service restarted during this run. Finding creation, observation submission and successful notice delivery remain unverified or blocked as specified above. CAR handoff has not been reached.

### Offline reload defect found during the live run

The signed-in production test captured an edit to question 8.1 while disconnected. It queued without a blocking dialog. A reload then exposed a blank application: the entry JavaScript, vendor JavaScript and stylesheet failed despite being present in Cache Storage. Diagnostics inside the actual service worker confirmed the module/CSS requests carried `Origin` and missed entries precached without that header under the server's `Vary: Origin` response.

Public static-asset cache reads now ignore `Vary` when matching the same requested URL, including retained previous-release assets. API and controlled-document requests remain outside this handler. The repair does not change authenticated-data caching or the backend.

On reconnection, the queued question 8.1 edit replayed automatically and returned HTTP 200 with committed version 2. The service-worker suite passed **7 tests**, including the added Origin-variant regression. The production browser asset test passed with an actual rendered login page after offline navigation and all declared module assets retrievable; the previous fetch-only assertion would not detect this blank-page defect. Signed-in audit reload acceptance is tracked separately below.

The repaired signed-in audit was then edited offline again and reloaded while disconnected. The checklist remained usable, displayed one pending change and retained the exact question 8.1 note. Reconnection automatically returned HTTP 200, committed version **3**, with the exact note in the server receipt (`offline-reload-replay.json`).

Visual inspection of that successful reload revealed an unrelated error toast. Capturing the portal error event identified `fetch-network:POST:/platform/product-events` as its source. Product analytics now skips requests while disconnected, rechecks connectivity after waiting for an analytics slot, and marks transport attempts silent so a connection race cannot interrupt audit work. This failure was telemetry noise, not loss of the queued checklist edit. Genuine save/validation failures remain visible.

The analytics, request-recovery and service-worker checks passed **16 tests**. The updated application built successfully, and the final TypeScript and heavy-route checks passed. The completion action now says **Completion requested** for a retained local request, so its label does not imply that the server has completed fieldwork.

### Browser restart, attachments and completion request

After loading the updated production frontend, all four finding forms were parked through their visible controls. Each classification dropdown exposed Critical, Major, Minor and Observation. These forms were not resubmitted to the failing backend.

The normal Complete fieldwork action retained a local completion request. Its actual outstanding checks were: four question edits not submitted, four finding drafts awaiting submission, and three questions not verified. It did not advance the server lifecycle.

Using question 8.1's attachment control and normal file chooser while offline, the auditor selected `SIMULATED_WORKFLOW_TEST_audit_notice.pdf` (8,714 bytes). This is the generated test audit notice, explicitly named as synthetic workflow evidence rather than operational compliance evidence. The UI reported one pending attachment. The browser was then closed completely and reopened with the same local persistent profile, still disconnected, at a 390px viewport.

The offline cold start recovered **186 / 189** answers, all four finding drafts, the completion request and the pending attachment. No error alerts appeared. Reconnection automatically uploaded the file: HTTP **200**, artifact **ID-OP28QDT1**, committed question version **4**, `offline_upload_state: SYNCED`, `server_processing_state: AVAILABLE`, and SHA-256 `71e3a7eff34f0657fb9e894e2614d1285fb291058a4d9a09a960c74a4340c96f`. The attachment's pending badge cleared. Receipts and restart screenshots are retained with the runtime evidence.

The uploaded file subsequently appeared in question details. Opening it with the frontend download control returned a PDF whose SHA-256 matched both the original selected file and the server artifact receipt. Uploading the synthetic file did not automatically mark it as evidence relied upon for the compliance assessment.

This verifies the observed QMS capture/reload/restart/replay paths. It does not certify every DMS or other-module workflow, actual camera hardware, a physically separate device, or a live session left disconnected for a full day. Beyond-day retention has an automated journal test, separately identified above.

Mobile visual review found that four saved-finding buttons overflowed their notice. The draft list now wraps with 44px targets, quieter token-based buttons and a shorter label. Remaining frontend UX work includes moving/adapting the floating release control so it does not compete with lower question fields, and supporting explicitly retained encrypted copies of synchronized evidence for offline review: the current evidence viewer exposes metadata only while offline. These limitations prevent any claim of complete offline functionality across every auditor action.

The rebuilt production page was checked at 320px and 390px: all four draft buttons fit within their panel and each measured 44px high. The repaired screenshot is `mobile-drafts-repaired.png`. Final state remains **186 / 189**, with the four protected drafts and a local completion request. No successful finding/CAR creation, recipient email delivery or advancement to Closing is claimed.
