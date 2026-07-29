# Documentation Assisted Search and Navigation

Date: 2026-07-29  
Scope: Publications reader and Document Control documented-information graph

## 1. Purpose

The assisted-search layer helps an authorised user locate controlled information, open the exact page or section, and identify linked forms, checklists, procedures, work instructions and record series. It does not replace the controlled source and cannot make approval, publication, acknowledgement, compliance or record-disposition decisions.

## 2. Authoritative-data boundary

1. The backend resolves the active AMO tenant from the authenticated session.
2. Document access is evaluated before retrieval using the existing Document Control profile and restriction scope.
3. Other documents are searched only at their current published revision.
4. The exact revision currently open in the reader may be included when the user is already authorised to read it.
5. Retrieval returns server-built navigation targets. An AI provider cannot invent or alter a URL, page, code, revision or access decision.
6. The controlled document displayed by the reader remains authoritative.

## 3. Retrieval pipeline

The endpoint is:

`POST /doc-control/workspace/t/{tenant_slug}/knowledge/assist`

The pipeline performs:

- exact document-code and alias matching;
- title and documented-information type matching;
- PostgreSQL full-text retrieval over controlled section headings and block text;
- SQLite-compatible phrase and token fallback for development and tests;
- result scoring and deduplication by revision and controlled location;
- page, section, anchor and hierarchy-path construction;
- immutable audit-event recording using only a query hash and result identifiers.

PostgreSQL GIN indexes are introduced for:

- `manual_blocks.text_plain`;
- `manual_sections.heading`;
- manual code, title and type identity.

The indexes operate on existing indexed text. They do not modify, reconstruct or copy the approved source PDF.

## 4. Optional external AI synthesis

Assisted retrieval works with no external provider. Optional synthesis is fail-closed and requires all of the following server-side settings:

```env
DOCUMENT_AI_PROVIDER=openai
DOCUMENT_AI_ALLOW_EXTERNAL=true
DOCUMENT_AI_MODEL=<approved model identifier>
OPENAI_API_KEY=<secret-store value>
```

Defaults:

```env
DOCUMENT_AI_PROVIDER=disabled
DOCUMENT_AI_ALLOW_EXTERNAL=false
```

When enabled:

- only the top permission-filtered snippets are sent;
- no source file, full manual or browser credential is sent;
- the provider request uses the fixed HTTPS Responses endpoint;
- response storage is disabled in the request;
- structured JSON output is required;
- provider source identifiers are validated against server-issued identifiers;
- a response without at least one valid controlled-source citation is rejected;
- any provider error falls back to deterministic retrieval;
- retrieved content is treated as untrusted data and cannot issue model instructions.

External synthesis must remain disabled until the organisation has approved its data-processing, confidentiality and retention position.

## 5. Frontend integration

The frontend exposes the same assistant in:

- the Publications reader, with the current manual and revision context;
- every Document Control workspace, with tenant-wide authorised search.

Modes:

- **Ask**: optional synthesis over permission-filtered results;
- **Search**: deterministic ranked results;
- **Navigate**: strongest controlled location first.

Source cards display the document code, title, heading, page, hierarchy path, executable-template status and indexed snippet. Opening a source uses the common route navigation contract:

```text
/maintenance/{AMO}/publications/{manual_id}/rev/{revision_id}/read?page={page}&anchor={anchor}
```

A route/event bridge scrolls the reader to the exact page, section or anchor and briefly highlights the destination. Existing links that already use `?page=` now follow the same contract.

## 6. Security controls

- API key is server-only and never returned to the browser.
- Tenant identity is derived from the authenticated user, not trusted from request data.
- Restricted-document filtering occurs before text retrieval and before provider invocation.
- Search results expose only current effective revisions, except for the exact authorised reader context.
- Query text is not retained in `manual_ai_hook_events`; only SHA-256, length, actor, context, mode and source IDs are stored.
- Provider output cannot perform a mutation.
- The assistant has no upload, approval, publication, acknowledgement, form-submission or record-review capability.
- Plain text is rendered in the UI; provider HTML is not accepted.

## 7. Performance controls

- GIN full-text indexes support large controlled libraries.
- Result sets are hard-limited to 20 and provider context to 8 sources.
- Snippets are bounded before an external request.
- Provider timeout is 12 seconds and failure is non-blocking.
- Search does not open or parse source PDFs at query time.
- Reader navigation uses existing virtualised page placeholders, so jumping to a distant page does not render intervening pages.

## 8. Deployment

1. Back up the database according to the production backup precheck.
2. Deploy backend and frontend from the same commit.
3. Run `alembic -c backend/amodb/alembic.ini upgrade heads`.
4. Leave the external provider disabled.
5. Verify deterministic searches for a document code, phrase, form and checklist.
6. Verify a restricted user cannot retrieve a restricted document by code or phrase.
7. Verify direct `?page=` navigation and assistant navigation in PDF and text readers.
8. Enable external synthesis only after an approved security decision and secret-store configuration.

## 9. Rollback

Application rollback:

- deploy the previous application commit;
- leave `DOCUMENT_AI_PROVIDER=disabled`;
- the new endpoint and UI disappear without affecting controlled documents or retained records.

Database rollback, only when explicitly authorised:

```bash
alembic -c backend/amodb/alembic.ini downgrade document_control_20260729_knowledge_graph
```

This removes only the assisted-search indexes. It does not remove hierarchy, reference or record data. Normal production rollback should leave harmless indexes in place unless there is a measured reason to remove them.

## 10. Acceptance criteria

- no unresolved PR review threads;
- clean and legacy-overlap migrations pass;
- backend route and security contracts pass;
- Publications and Document Control production builds pass;
- integrated Quality, Accounts, Workforce, Rostering, realtime and offline gates pass;
- direct and assisted navigation target the same controlled page or section;
- deterministic search remains available with no provider configured;
- provider failure never blocks ordinary document access;
- all displayed answers include controlled source cards and the authority disclaimer.
