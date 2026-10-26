# Checklist workspace review — 17 October 2026

Frontend revision only; no backend files changed. See also [the broader live UX review](portal-ux-live-review-2026-10-17.md).

## Implemented

- Hide the lifecycle rail in Fieldwork. Use the actual audit title, reference, small progress meter and quiet connection state in a compact header. Remove the duplicate stage title, explanatory paragraph and source-preservation footer. Move the persistent summary, schedule and source review into the active-personnel disclosure.
- Keep answer headers within the checklist scroll region and display the actual source labels beside every radio. Phones keep each question, choices and remarks together. Fix older mobile styles that stretched the compact header vertically.
- Open details directly beneath the question. Lead with criteria, regulatory/manual references and the verification plan; collapse advanced assessment controls. Show previous findings/CAPs only when their explicit question identifiers match the retained package.
- Put a paperclip beside remarks with multiple-file upload and a camera option. Files enter the encrypted device queue before upload. Existing replay retains files until server receipt/hash verification; failed local storage never reports success.
- Remove the full-page workflow failure modal and degraded class. Refresh errors retain usable audit/session/checklist data and the last loaded authorized write window. Assignment, preparation and completed-audit restrictions remain effective. Errors inside closed disclosures no longer generate global toasts.
- Automatically retain the issued checklist package and debounce updates when checklist, binding or finding data changes. Warm service-worker assets in the background. Controlled reference downloads do not gate local capture and remain an additional operation; a cached checklist does not imply every PDF is downloaded.
- Encrypt and persist remarks, samples, assessment drafts, response drafts, finding drafts and completion requests. Serialize journal writes, acknowledge transaction completion, and hydrate before editing. Pending work has no time expiry. Expired package refresh deadlines do not erase retained contents; server authorization/version checks still apply on replay.
- Allow the lead auditor to record a completion request locally. Submit it from the audit workspace after reconnection, queue synchronization and required checks. Retain rejected requests for review. A pending request does not falsely mark the lifecycle complete.

## Verification

- 24 focused unit/contract tests passed, including recovery three days later, encryption, user/tenant isolation, failed-write preservation and expired-package recovery.
- 12 checklist/theme/realtime browser checks passed, plus a separate regression for closed-disclosure errors. They cover actual upload/camera controls, encrypted evidence across reload, inline detail placement, source labels, 172 parsed questions, touch sizing and reduced motion.
- Authenticated live audit inspection passed: compact desktop header, no lifecycle rail, inline context, checklist retained after connection loss, no offline modal/background error toast, and a compact 390px layout without horizontal document overflow. Screenshots are under `.artifacts/live-verification/playwright/portal-ux-live-live-audit--fb8ac-ection-loss-without-a-modal/`.
- The verification account is not an assigned auditor. These live checks establish rendering and cached continuity, not successful live auditor writes, server completion acceptance or independent-device convergence.

## Backend and remaining UX work

1. Repair the operational 236-question binding through the source-rebuild path, which previously returned HTTP 500. The parser produces 172 assessment questions. The frontend does not silently rewrite existing audit records.
2. Resolve the reported fieldwork mutation and evidence/workflow response failures with database regression checks. No backend fixes are claimed here.
3. Supply stable cross-revision question identity and explicit links to previous evidence, findings and CAP revisions, including authorized attachment downloads. Current history shows explicitly matching retained records; it does not infer matches from similar prose.
4. Provide an idempotent, versioned completion/sign-off command and receipt contract, including captured-at identity, conflict/revocation rules and audit trail. Current requests persist and submit from the audit workspace; completion replay from any portal page is not implemented. A closed browser cannot execute authenticated replay.
5. Exercise assigned lead/supporting-auditor offline writes, next-day browser restart with the production service worker, physical iOS/Android camera/keyboard behavior, receipt-based evidence cleanup and simultaneous changes from independent devices before certifying those outcomes.

Production build, modal-layer check, CSS contract (126 stylesheets) and heavy-route chunk check passed. Progress now counts durably queued responses and recorded N/C reasons while retaining a separate pending-sync indication.

Final verification: 28 focused tests, 13 checklist/theme/realtime browser checks and all four authenticated live audit/DMS checks passed. The final TypeScript check passed. Backend `/livez` returned HTTP 200, and the backend working tree remains unchanged.
