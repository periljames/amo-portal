# Documentation Assisted Search and Navigation

Date: 2026-07-29  
Updated: 2026-08-20  
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

PostgreSQL GIN indexes are introduced for `manual_blocks.text_plain`, `manual_sections.heading`, and manual code/title/type identity. The indexes operate on existing indexed text. They do not modify, reconstruct or copy the approved source PDF.

## 4. Governed external AI synthesis

Assisted retrieval works without an external provider. Optional synthesis is fail-closed and is routed through the platform AI control plane. Document Control must not read an OpenAI key or model directly from environment variables and must not call the provider endpoint itself.

External synthesis requires all of the following:

- an enabled OpenAI provider credential in the platform or tenant provider registry;
- an active tenant `ai` module subscription;
- a tenant AI plan that permits the selected model;
- tenant policy permission to send authorised controlled-document excerpts externally;
- available tenant AI budget when a monthly budget is configured.

The authenticated SQLAlchemy session, AMO ID and actor user ID are passed explicitly into the governed AI gateway. No process-global or thread-local request context is used to convey tenant identity.

When enabled:

- only the top permission-filtered snippets are sent;
- no source file, full manual or browser credential is sent;
- provider credentials remain encrypted and server-side;
- the OpenAI Responses adapter sends `store: false`;
- paid provider tools are not enabled by this workflow;
- provider usage accounting is required before the request is accepted as successful;
- token usage and provider cost are metered to the tenant by the common AI gateway;
- the request is audited with model, rate snapshot, usage and a prompt hash rather than retained prompt text;
- provider source identifiers are validated against server-issued identifiers;
- a response without at least one valid controlled-source citation is rejected;
- any provider or policy failure falls back to deterministic retrieval.

Tenant activation, model tier, external-document permission and budget are managed in the Platform AI Control Centre. They are not deployment environment switches.

## 5. Frontend integration

The frontend exposes the same assistant in the Publications reader and in Document Control library contexts. It remains contextual rather than becoming permanent chat-first DMS chrome.

Modes:

- **Ask**: optional governed synthesis over permission-filtered results;
- **Search**: deterministic ranked results;
- **Navigate**: strongest controlled location first.

Source cards display the document code, title, heading, page, hierarchy path, executable-template status and indexed snippet. Opening a source uses the governed Document Control route while preserving revision, page and anchor context.

## 6. Security controls

- Provider API keys are encrypted server-side and are never returned to the browser.
- Tenant identity is derived from the authenticated user and passed explicitly into the AI gateway.
- Restricted-document filtering occurs before text retrieval and before provider invocation.
- Search results expose only current effective revisions, except for the exact authorised reader context.
- Query text is not retained in `manual_ai_hook_events`; only SHA-256, length, actor, context, mode and source IDs are stored.
- The common platform AI audit log records metering evidence without storing the raw prompt.
- Provider output cannot perform a mutation.
- The assistant has no upload, approval, publication, acknowledgement, form-submission or record-review capability.
- Plain text is rendered in the UI; provider HTML is not accepted.
- A tenant-specific provider override cannot silently fall back to another tenant's credential.

## 7. Performance and cost controls

- GIN full-text indexes support large controlled libraries.
- Result sets are hard-limited to 20 and provider context to 8 sources.
- Snippets are bounded before an external request.
- Provider requests have a bounded timeout and deterministic retrieval remains available on failure.
- Search does not open or parse source PDFs at query time.
- Reader navigation uses existing virtualised page placeholders, so jumping to a distant page does not render intervening pages.
- Input, cached-input and output tokens are metered separately by the platform AI gateway.
- Provider cost is calculated from the model rate snapshot used for that request.

## 8. Deployment

1. Back up the database according to the production backup precheck.
2. Deploy backend and frontend from the same commit.
3. Run `alembic -c backend/amodb/alembic.ini upgrade heads`.
4. Keep tenant AI disabled unless the tenant has an approved AI entitlement and external-document policy.
5. Configure the OpenAI credential through the encrypted provider registry / Platform AI Control Centre, not `.env`.
6. Verify deterministic searches for a document code, phrase, form and checklist.
7. Verify a restricted user cannot retrieve a restricted document by code or phrase.
8. Verify direct and assisted page/anchor navigation.
9. If external synthesis is authorised, verify the tenant budget, model tier, metering and audit evidence using a controlled test request.

## 9. Rollback

Application rollback should deploy the previous application commit and disable the tenant AI module through the control plane. The controlled documents and deterministic search index remain intact.

Database rollback, only when explicitly authorised:

```bash
alembic -c backend/amodb/alembic.ini downgrade document_control_20260729_knowledge_graph
```

This removes only the assisted-search indexes. It does not remove hierarchy, reference or record data. Normal production rollback should leave harmless indexes in place unless there is a measured reason to remove them.

## 10. Acceptance criteria

- no direct Document Control OpenAI API key/model environment path remains;
- no direct Document Control provider-network call remains;
- authenticated tenant/user context reaches AI synthesis explicitly;
- tenant AI entitlement, model tier, external-document permission and budget are enforced before provider invocation;
- token and cost usage is recorded through the common AI meter;
- provider response storage is disabled by the OpenAI adapter;
- backend route/security contracts pass;
- direct and assisted navigation target the same controlled page or section;
- deterministic search remains available with no provider configured;
- provider failure never blocks ordinary document access;
- all displayed answers include controlled source cards and the authority disclaimer.
