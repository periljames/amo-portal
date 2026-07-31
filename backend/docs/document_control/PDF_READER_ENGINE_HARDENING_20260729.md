# Controlled PDF Reader Engine Hardening

Date: 2026-07-29  
Scope: Publications reader, Document Control linked resources, completed PDF records, and reader-specific CI  
Base: `main` after PR #376

## 1. Purpose

Improve the existing controlled-document reader without replacing its routes, visual identity, document-control records, permissions, revision model, or exact-source streaming contract.

The browser remains a portal-native reader. PDF.js remains the progressive browser renderer and text/form interaction layer. PDFium is introduced behind a narrow server-side adapter for validation, deterministic flattening, and retained-record output. Chrome-specific UI, extension messaging, browser-process integration, PDF JavaScript execution, and print-preview code are not imported.

## 2. Non-negotiable preservation rules

1. The uploaded approved PDF remains immutable and byte-for-byte authoritative.
2. Reader zoom, search, field entry, annotations, working copies, downloads, flattening, and record creation never rewrite the approved source path.
3. Draft markings remain non-destructive reader overlays; draft downloads continue to use the controlled derivative path.
4. Every reader, flatten, and submit route enforces tenant scope and the same manual access profile as the canonical Publications reader.
5. A completed retained record is created only from a published immutable template revision and its checksum is calculated after server-side PDFium processing.
6. PDF JavaScript and dynamic XFA fail closed. No browser or server JavaScript embedded in a PDF is executed.
7. Form entry is local until an explicit download or submit action. Closing or switching documents cannot silently submit evidence.
8. Server-side flattening runs with bounded input size, bounded pages, bounded execution time, temporary-path confinement, and cleanup on success or failure.
9. Search, outline inspection, form inspection, and reference indexing are optional progressive tasks. None may block first-page rendering.
10. The reader must always render a useful error state rather than a blank route.

## 3. Target architecture

### Browser layer

`PdfReaderEngine` is the only browser-facing PDF engine contract. It owns:

- stable authenticated PDF.js document inputs;
- nearby-page rendering and page geometry;
- page, fit-width, fit-page, and percentage zoom;
- progressive full-document text search;
- active-result navigation and visible text highlighting;
- outline extraction;
- form-field and PDF-JavaScript inspection;
- safe AcroForm fill mode;
- working-copy serialization through `PDFDocumentProxy.saveDocument()`;
- user-and-document-partitioned IndexedDB draft storage;
- original, editable, flattened, and retained-record actions;
- keyboard and accessibility behaviour;
- explicit teardown of loading, render, search, and autosave work.

React components may consume the adapter but may not create independent PDF loading-task rules or inline React-PDF `options` objects.

### Server layer

`pdfium_service.py` is the only module permitted to import `pypdfium2` or raw PDFium bindings. It owns:

- PDF signature and size validation;
- page-count and form-type inspection;
- JavaScript and dynamic-XFA rejection;
- page-by-page normal-display flattening;
- post-flatten reopen validation;
- output page-count verification;
- SHA-256 generation;
- temporary-file confinement and cleanup;
- deterministic error codes safe for API clients.

The service does not own authorization, database transactions, record numbering, retention, or audit events. Routers perform authorization and pass validated output to the existing retained-record service.

## 4. Reader command surface

The initial reader command bar contains only:

- previous page;
- page number and page count;
- next page;
- zoom out;
- zoom percentage;
- zoom in;
- fit width / fit page;
- search;
- fill form when allowed;
- download menu;
- compact More menu.

Table of contents, linked references, form status, reader preferences, document metadata, citation, reporting, and advanced controls remain available progressively. They must not occupy a permanent wall above the first page.

## 5. Output definitions

### Original controlled source

Exact authorized source or existing controlled derivative. No form values from the current session are written into this output.

### Editable working copy

PDF.js-saved PDF containing current AcroForm values. It remains editable and is not a controlled record. Filename must visibly include `WORKING_COPY`.

### Flattened copy

Server-generated PDFium output in which supported annotations and form fields are part of page content. It is a user download, not automatically a retained record. Filename must visibly include `FLATTENED`.

### Retained record

Server-generated PDFium flattened output passed to `create_documentation_record`. It receives the existing record number, checksum, template revision, retention, submitter, originating reference when present, and audit custody.

## 6. Four implementation phases

### Phase 1 — Clean reader, zoom, search, and navigation

- introduce the browser engine adapter;
- replace duplicated loading-task behaviour with one core reader;
- preserve continuous nearby-page rendering;
- add fit width, fit page, custom zoom, page entry, and keyboard shortcuts;
- add progressive PDF text search with next/previous result and highlighting;
- keep first-page rendering independent of outline, forms, references, and search;
- keep the current CSS language while reducing initial chrome.

### Phase 2 — Form filling and durable local working copies

- detect AcroForm fields and JavaScript without blocking rendering;
- allow fill mode only for authorized `PDF_ACROFORM` or `HYBRID` execution profiles;
- render forms only while fill mode is active;
- autosave serialized working copies to IndexedDB when the profile permits drafts;
- partition drafts by user, tenant, manual, and revision;
- restore, replace, discard, and download working copies explicitly;
- protect dirty documents during close, route change, and source replacement;
- retain external-link safety and keep PDF JavaScript disabled.

### Phase 3 — PDFium flattening and immutable record output

- pin `pypdfium2==5.12.1`;
- add direct-reader and linked-resource flatten endpoints;
- flatten normal AcroForm/annotation pages through PDFium;
- reject JavaScript-bearing and dynamic-XFA documents;
- reopen and verify every output before returning or retaining it;
- use the same service for flattened downloads and submitted retained records;
- include engine version, flatten result, source checksum, output checksum, page count, and output mode in record metadata;
- preserve existing transaction-aware artifact cleanup.

### Phase 4 — Engine hardening, fallback, and acceptance

- expose reader capabilities before enabling form actions;
- use PDF.js rendering with server PDFium validation rather than shipping a browser PDFium/WASM bundle by default;
- return explicit unsupported reasons instead of damaged output;
- keep the adapter boundary ready for a future measured WASM renderer only when representative-document fidelity proves it necessary;
- test normal PDFs, image-only PDFs, AcroForms, annotations, JavaScript-bearing PDFs, malformed PDFs, encrypted PDFs, dynamic XFA, large PDFs, source changes, cached progress changes, offline draft recovery, and concurrent submissions;
- run exact-head CI and repeated Codex review until no actionable thread remains.

## 7. API contract

### `GET .../pdf-capabilities`

Returns:

- execution profile and submission mode;
- source checksum and page count;
- `can_fill`, `can_save_draft`, `can_download_original`, `can_download_working`, `can_flatten`, and `can_submit`;
- `has_acroform`, `has_javascript`, `is_dynamic_xfa`, and `unsupported_reason`;
- browser renderer and server processor identifiers.

### `POST .../flatten.pdf`

Accepts a completed PDF working copy. Returns a no-store flattened PDF with source/output checksum and page-count headers. It does not create a record.

### `POST .../submit-record`

Accepts a completed PDF working copy and JSON metadata. Produces a PDFium-flattened retained record through the existing record service.

The linked-resource submit route uses the same processing function and retains the originating reference.

## 8. Permanent CI gates

### Reader source contract

CI fails when:

- a React-PDF `Document` uses an inline `options` object;
- a second reader creates an independent PDF loading-task implementation;
- first-page `onLoadSuccess` awaits outline, search, form, or JavaScript inspection;
- reader reset depends on `initialPage` rather than source identity;
- `renderForms` is enabled without an execution-profile and fill-mode gate;
- PDF JavaScript execution is enabled;
- a controlled source is fetched into a full browser Blob before normal reading;
- working-copy storage lacks user, tenant, manual, and revision partitioning;
- download labels do not distinguish original, working, flattened, and retained outputs.

### PDFium contract

CI fails when:

- `pypdfium2` is imported outside `pdfium_service.py` and its tests;
- the dependency is unpinned or the yanked `5.12.0` release is used;
- flattening output is not reopened and page-count checked;
- temporary paths can escape the configured work directory;
- JavaScript or dynamic XFA is not rejected;
- failed processing leaves temporary files;
- direct and linked submissions use different flattening implementations.

### Functional tests

The suite must prove:

1. ordinary PDF validation;
2. AcroForm detection;
3. editable working-copy save;
4. page-by-page flattening;
5. flattened output reopens with the same page count;
6. output checksum differs only when content changes;
7. original source bytes remain unchanged;
8. malformed, oversized, scripted, and unsupported PDFs fail closed;
9. authorization occurs before processing;
10. direct and reference-based submissions create correct immutable record metadata;
11. search cancellation and source replacement do not leak stale results;
12. cached position refresh does not clear loaded pages;
13. local drafts are isolated across users and tenants;
14. keyboard shortcuts do not override text-entry controls;
15. first-page rendering is independent of optional inspection failures.

### Workflow requirements

`Publications Reader CI` must run:

- backend compile for manuals and PDF engine modules;
- focused PDFium service tests;
- reader source-contract tests;
- frontend reader unit tests;
- TypeScript and Vite production build.

`Document Control Domain CI` must additionally run:

- clean PostgreSQL migration;
- mapper and route precedence checks including all PDF reader routes;
- all Document Control tests;
- PDFium retained-record tests;
- frontend production build;
- no-seeded-data checks.

The integrated release gate remains mandatory on the final head.

## 9. Performance budgets

- first page is schedulable before full-document text search or outline completion;
- no more than seven nearby pages render at once in continuous mode;
- text search uses bounded concurrency and is cancellable;
- form autosave is debounced and never runs more than one serialization concurrently;
- IndexedDB working copies are limited to 100 MB per document and old revisions are replace-not-append;
- flatten endpoints reject inputs over 100 MB and documents over the configured page ceiling;
- server processing uses a bounded timeout and no incremental append to an untrusted input;
- reader-specific production chunk growth is reported and must remain within the repository lazy-route budget.

## 10. Security acceptance

- tenant and manual access are checked before file bytes are read;
- filenames are sanitized and response headers use `no-store` and `nosniff`;
- raw storage paths never enter API responses;
- embedded JavaScript is never executed;
- external links open with `noopener` and `noreferrer` behaviour;
- dynamic XFA and encrypted PDFs without an approved password workflow fail closed;
- flattening uses normal-display mode and does not invoke printing, shell, network, font download, or external programs;
- submitted output is hashed after flattening and before database commit;
- original and working-copy checksums are retained in audit metadata.

## 11. Definition of done

The PR is mergeable only when:

- all four phases are implemented;
- no temporary applicator or write-enabled CI remains;
- Publications Reader CI, Document Control Domain CI, and the integrated release gate pass on the exact final SHA;
- every Codex finding is fixed, answered with exact-head evidence, and resolved;
- a final Codex review returns no actionable finding;
- the PR is current with `main`, non-draft, mergeable, and unmerged.
