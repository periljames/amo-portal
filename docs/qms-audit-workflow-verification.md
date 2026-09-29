# Audit workflow verification

Changes reviewed on 2026-09-28. No live notices were sent and no tenant records were altered during verification.

## Automated checks

- Checklist selection: repeating a successful DMS selection returns the saved binding without creating questions again; empty issued checklists are rejected.
- Cache recovery: preparation context, revisions, bindings and session authority cannot be restored from stale HTTP/offline or persisted query caches.
- Setup: definition and saved team requirements, notice periods and meeting chronology.
- Preparation: fieldwork remains gated by issued preparation.
- Later stages: execution and follow-up remain separate; report/CAR linkage, required evidence, archive gates and closed-audit immutability retain their existing checks.
- Notices: the mocked delivery test verifies approval, the signed PDF attachment and recorded delivery events.
- Shared UI: modal top-layer and toast policy contracts; existing setup and stage-routing tests.

Results: 28 backend tests and 38 frontend tests passed. Production build, modal-layer checks and heavy-route chunk checks passed.

## Changes requiring visual confirmation

- Bind a current DMS checklist, revisit Prepare, and verify the checklist count and release readiness.
- Repeat selection and confirm there are no duplicate questions.
- Clear a recommendation, change document type, or filter the library; verify the visible selection is the submitted document.
- Submit a blank checklist form; verify required-field guidance. Check whitespace-only questions and a source without an effective revision.
- Append to pre-existing checklist rows, including rows without a template binding.
- Create/review a document request; verify missing controlled-document guidance and action feedback.
- Invite with a past expiry, copy an invitation link, and revoke access; verify validation and confirmation.
- With mocked mail delivery, check successful, partial, failed and already-delivered notice results while the preview remains open.
- Open another dialog while a toast is visible; verify feedback remains readable and dismissible above the dialog.

The in-app browser connection failed before opening a page, so these visual scenarios are not marked verified. Shared components and existing design tokens are reused; no separate notification or modal system was introduced.
