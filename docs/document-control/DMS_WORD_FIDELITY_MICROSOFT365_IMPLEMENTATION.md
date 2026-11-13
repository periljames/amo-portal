# AMO Portal — DOCX Layout Fidelity and Microsoft 365 Working Documents

**Repository:** periljames/amo-portal  
**Implementation branch:** feat/dms-word-fidelity-m365-20261028  
**PR:** #569 (one draft PR targeting main)  
**Base main SHA:** 86a66d2d3630518a67ff3f02d5c9467cdcdfd90d  
**Status:** Coding delivered in Phases 1–2. Phase 3 test execution, security verification and browser acceptance deferred by request.

## Operating decision

Word remains the ordinary authoring tool. Authors may continue editing offline or in
SharePoint. AMO Portal retains the exact uploaded DOCX, manages immutable revisions and
controls approval, authority, effectivity, distribution, supersession and acknowledgement.

**Do not label LibreOffice or docx-preview output as an exact Word original.**
A PDF rendition generated from DOCX is derived content. Where source-layout fidelity
matters, a controller may upload a PDF exported in desktop Microsoft Word and explicitly
verify that rendition. An original PDF uploaded as PDF remains the authoritative source.

## Phase 1: code changes

- Canonical Manual and ManualRevision identities, Document Control workflows, approval
  guards, PDF.js reader, offline source cache and distribution contracts remain intact.
- The backend retains the original Office source and SHA-256 checksum.
- Added manual_revision_renditions, keyed by canonical revision ID; records converter,
  PDF checksum, page count, source media count, PDF raster-image count, attempts,
  conversion errors and human verification evidence.
- Existing LibreOffice conversion precompute now persists PROCESSING/READY/
  REVIEW_REQUIRED/FAILED instead of leaving failures only in server logs.
- Missing rendered images may be flagged for review (vector drawings can legitimately
  have no PDF raster image objects; this heuristic is **not** a fidelity guarantee).
- Added GET layout-status, POST layout-retry, POST layout-verify and POST layout-upload,
  with tenant/role checks, draft immutability guards and checksum binding.
- The reader now uses existing PDF.js for Office PDFs when available. Failed or
  processing Office conversions show truthful status with original-DOCX download,
  accessible text and an opt-in, explicitly approximate docx-preview. Approximate
  rendering must not be represented as approved page layout.
- Word PDF upload only applies to editable drafts and is blocked after verification
  or entry into decision stages. The original DOCX is not overwritten.
- Word documents cannot publish without a usable PDF rendition. Regulated or
  critical manuals additionally require human verification of the derivative checksum.

## Phase 2: code changes

- Added tenant-scoped Microsoft connection and SharePoint link tables and models.
- OAuth 2.0 authorization-code flow uses ten-minute, one-time, hashed state;
  callback authorization is limited to a current tenant administrator.
- Microsoft refresh credentials are encrypted using the existing platform
  secrets facility. Raw secrets and tokens must never reach the browser.
- Graph API requests are server-side; only the Microsoft Graph origin is called
  with bearer credentials. Preauthenticated SharePoint download URLs receive
  **no** bearer token, are HTTPS-host validated and stream under a size limit.
- Tenant administrators connect/disconnect under Document Control Administration.
  DMS controllers can link a SharePoint Word working file to an existing canonical
  manual, check its eTag, open in Word, unlink with audit history and import a
  deliberately selected eTag as a fresh DMS draft revision.
- The importer validates that the DOCX's recognized manual and revision identity
  do not conflict with the requested DMS identity. It rechecks the SharePoint
  eTag both before and after download, preserving an exact imported checksum and
  provider version provenance. It uses the existing DOCX ingestion pipeline.
- A SharePoint save NEVER publishes a DMS revision and never changes an already
  approved source. Word access is optional for operational readers.
- No automatic/unattended Graph synchronization is implied: the UI offers explicit
  "Check for changes" and "Import Word revision" actions. Automatic monitoring may
  follow only after the consent, notification and replay-safety policies are settled.

## Microsoft 365 deployment configuration

Register a multi-tenant or organization-approved Microsoft Entra web application.
Authorize the exact HTTPS backend callback URL:

    /doc-control/microsoft365/oauth/callback

Supply deployment secrets and public URLs via secret manager:

    DMS_MICROSOFT_CLIENT_ID
    DMS_MICROSOFT_CLIENT_SECRET
    DMS_MICROSOFT_REDIRECT_URI=https://<api-domain>/doc-control/microsoft365/oauth/callback
    DMS_MICROSOFT_FRONTEND_URL=https://<portal-domain>
    PLATFORM_SECRETS_KEY=<existing production Fernet key>
    DMS_MICROSOFT_MAX_FILE_BYTES=62914560   # optional bounded default (60 MiB)

Use delegated User.Read, Files.Read.All and offline_access, with openid/profile
for the authorization flow. Microsoft 365 tenant consent/permissions must be
approved according to the customer's security policy. This is a read-only
working-file connector; it does not require SharePoint write permissions.
A connected account can only resolve files permitted to that account. Linking
uses a SharePoint HTTPS sharing URL for a DOCX (not a browser-local file path).

Production must configure both TLS and the trusted Microsoft application
credentials. Never put the client secret or tokens into JavaScript, the tenant
metadata JSON or an audit log. The existing platform secrets encryption key
must remain stable across deployments.

## Existing source mapping

| Responsibility | Path |
|---|---|
| Canonical source revision and SHA-256 | backend/amodb/apps/manuals/models.py |
| Original upload/semantic parsing | backend/amodb/apps/manuals/core_router.py |
| Word PDF conversion | backend/amodb/apps/manuals/office_layout.py |
| Rendition ledger and review | backend/amodb/apps/manuals/office_rendition.py |
| Rendition API | backend/amodb/apps/manuals/office_rendition_router.py |
| Reader metadata and PDF streaming | backend/amodb/apps/manuals/publications_fast_reader_router.py |
| Unified reader and approximate preview | frontend/src/pages/manuals/PublicationsReaderPage.tsx |
| Source-specific React preview | frontend/src/pages/manuals/PublicationDocxLayoutViewer.tsx |
| Microsoft connection and link models | backend/amodb/apps/doc_control/microsoft_models.py |
| Graph provider and import workflows | backend/amodb/apps/doc_control/microsoft_graph.py, microsoft_router.py |
| Microsoft provider UI | frontend/src/pages/documentControl/DocumentMicrosoftConnectionPanel.tsx, DocumentMicrosoftFilePanel.tsx |
| DMS Word rendition approval UI | frontend/src/pages/documentControl/DocumentWordRenditionPanel.tsx |

## Phase 3 — final verification and repair (not executed in coding phases)

1. Confirm live main/branch diff and safe rebase/merge, including outstanding
   library PR #557 and all route-register precedence contracts.
2. Alembic graph/head checks, clean PostgreSQL migration, ORM mapper setup,
   downgrade restrictions, controlled legacy data integrity.
3. Python compile/import, targeted backend permissions, source-checksum,
   invalid PDF/DOCX, conversion missing/failed, retry, author-export replacement
   and publication-blocker cases. Do not disable preexisting CI tests.
4. Microsoft connector tenant consent, state replay/expiry, token encryption/
   rotation, unauthorized linking, other-tenant access, rate limits, invalid
   URLs, malicious content, interrupted downloads and stale eTag conflicts.
5. Use an actual Microsoft Word authored reference set (including images,
   logos, floating shapes, tables, bookmarks, footnotes, section breaks,
   landscape pages, headers/footers, and 100+ page manuals). Compare the portal
   reading rendition against the Word exported PDF, not only PDF validity.
6. Browser acceptance: upload DOCX, pending view, successful conversion,
   original source download, accessibility mode, fallback warning, zoom,
   images, page navigation, print, draft status, approval and distribution.
7. Confirm a SharePoint-linked file can be opened in desktop Word or Word for
   web, updated, checked by Graph and imported exactly once per requested
   controlled revision, with provenance and without auto-publication.
8. Run scoped formatting/lint/typecheck/build, relevant backend/Playwright
   tests and the CI jobs affected by these changes; fix implementation
   defects without rewriting unrelated working modules.
9. Record concrete observed test outcomes, remaining issues and deployment
   configuration. Do not claim production/acceptance readiness before passing.

## Known limits / accepted design boundaries

- LibreOffice PDFs are not inherently identical to the source Word layout.
  A controller-provided Word PDF and explicit visual verification provides the
  reliable regulated-publication pathway.
- No Microsoft account is necessary to read a controlled document already
  imported into AMO Portal.
- This implementation intentionally does not embed the Microsoft Word editor.
  SharePoint opens with the organization's usual Microsoft 365 permissions and
  allows desktop Word or Word for the web.
- Automatic push sync is intentionally not implemented: it could silently
  supersede a controlled document without human-approved revision processing.
- This record is an implementation ledger, **not** a test pass report.
