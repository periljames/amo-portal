# Universal controlled-document reader architecture

## Purpose

The Publications reader must not be designed around one Maintenance Training Manual or one PDF structure. It must provide the same dependable reading, navigation, annotation, evidence, sharing and audit workflow across controlled documents while preserving each source revision exactly.

This plan separates the **source file**, **rendering adapter**, **canonical document model**, **user annotations** and **controlled-record actions**. A new format must plug into the adapter boundary without changing navigation, audit evidence, permissions or annotation custody.

## Immediate stability rule

Navigation requests are commands, not persistent reader state.

- A TOC, search, citation or internal-link request is consumed once.
- Manual scroll, wheel, touch, keyboard navigation or a completed destination releases that command.
- Fit, zoom, resize, reader-mode entry and virtualizer remeasurement must preserve the current reading anchor and must never replay an old destination.
- The physical viewport remains the only authority for the current page or document location.

## Canonical document model

Every approved revision should expose a format-neutral manifest keyed by the immutable source checksum.

```text
DocumentRevision
  tenant_id
  document_id
  revision_id
  source_sha256
  source_format
  classification
  control_status
  page_or_sheet_count
  adapter_version
  render_artifacts[]
  locations[]
  searchable_blocks[]
  links[]
  form_capabilities
  accessibility_capabilities
```

A canonical location must support both fixed-layout and reflowable documents.

```text
DocumentLocation
  revision_id
  adapter
  page_number?          # PDF, image, print proof
  sheet_name?           # spreadsheet
  slide_number?         # presentation
  section_id?           # DOCX, HTML, Markdown
  block_id?
  text_quote?           # exact + prefix + suffix
  normalized_bbox[]?    # one or more 0..1 rectangles
  character_range?
  source_checksum
```

All citations, highlights, notes, findings, deep links and saved positions must use `DocumentLocation`. They must never depend only on a transient DOM element or a generated CSS selector.

## Adapter contract

Each adapter must implement the same capabilities.

```text
inspect(source) -> capabilities + checksum
render(location, viewport) -> bounded visual surface
resolve_link(source_destination) -> DocumentLocation
locate(selection) -> DocumentLocation
search(query) -> ranked DocumentLocation[]
extract_text(location) -> text with provenance
export_view(location, options) -> controlled derivative
compare(revision_a, revision_b) -> change locations
```

### Required adapters

1. **PDF**
   - native PDF.js fixed-layout rendering;
   - internal destinations, outlines, annotations and AcroForm detection;
   - checksum-keyed safe derivative when scripting is present;
   - page and bounding-box anchors.

2. **DOCX and ODT**
   - server-generated immutable PDF proof for authoritative layout;
   - semantic section/block model for accessible reading;
   - headings, tables, footnotes, comments and tracked-change metadata;
   - quote and block anchors that survive visual reflow.

3. **XLSX and ODS**
   - workbook/sheet navigator;
   - frozen rows and columns, bounded virtualization and formula/value distinction;
   - cell/range anchors such as `Sheet1!B7:F14`;
   - print-area proof for controlled export.

4. **PPTX and ODP**
   - slide navigator and speaker-note access according to permission;
   - slide-object anchors and immutable slide proof;
   - presentation mode separate from controlled reader mode.

5. **HTML, Markdown and plain text**
   - sanitized semantic rendering;
   - stable heading, block and quote anchors;
   - accessible reflow and print proof.

6. **Images and scanned documents**
   - tiled rendering for TIFF, PNG and JPEG;
   - OCR as an indexed aid only, never a silent replacement for the source image;
   - confidence and OCR provenance displayed to the user.

Unsupported proprietary formats must be converted by a controlled server-side process into an immutable PDF proof plus extracted semantic content. The original file remains retained and downloadable according to permission.

## Annotation and highlighting model

Highlights must be revision-locked records, not paint added directly to a canvas.

```text
DocumentAnnotation
  id
  tenant_id
  revision_id
  source_sha256
  location
  type                 # HIGHLIGHT, NOTE, QUESTION, EVIDENCE, FINDING_LINK
  colour               # YELLOW, GREEN, BLUE, PINK, RED
  body?
  tags[]
  visibility           # PRIVATE, TEAM, AUDIT, CONTROLLED_RECORD
  created_by
  created_at
  updated_at
  superseded_by?
```

### Colour semantics

- **Yellow:** important or review later.
- **Green:** verified evidence or compliant requirement.
- **Blue:** reference, definition or supporting context.
- **Pink:** question, discussion or clarification required.
- **Red:** potential nonconformity, conflict or urgent risk.

Tenants may rename colour meanings, but stored colours remain standardized for export and accessibility.

### Required behaviour

- Selecting text or an area opens a compact annotation command bar.
- A highlight may include a note, tags and visibility.
- PDF selections store exact text quote, surrounding context and normalized rectangles.
- Reflowable selections store section/block identifiers and quote selectors.
- Spreadsheet selections store workbook, sheet and cell range.
- Annotations remain attached only to the exact revision checksum.
- When a new revision is issued, the portal proposes migrations but never silently moves evidence.
- Every migration records old location, new location, confidence and approving user.

## Audit workspace capabilities

The reader should support the actual work performed during audits and technical reviews.

### Evidence capture

- Pin a page, paragraph, table range, slide or image region as audit evidence.
- Add evidence directly to an audit checklist item, finding, CAR, change proposal or compliance matrix.
- Preserve document code, issue, revision, checksum, page/location, selected quote and capture timestamp.
- Export an evidence index with controlled links and page thumbnails where permitted.

### Review and comparison

- Side-by-side revision comparison.
- Added, removed and changed text indicators.
- Changed table cells, slide objects and page regions.
- Jump from revision history to the exact changed location.
- Accept or reject proposed annotation migration.

### Navigation and productivity

- One-shot TOC, search and internal-link navigation.
- Reader mode with `Esc` exit.
- Fit width, fit page and custom zoom without losing the reading anchor.
- Keyboard navigation and command palette.
- Saved places, recent locations and named bookmarks.
- Search within the document, linked publications and the authorized tenant corpus.
- Copy controlled citation and permission-checked deep link.
- Open linked regulation, procedure, form, finding or training requirement in a side panel.

### Reliability

- Bounded virtualization and render queues.
- No unfinished canvas exposure.
- Completed pages retained until bounded eviction.
- Offline cache keyed by revision checksum.
- Recovery of saved position and private annotations after reconnect.
- Performance telemetry that records timings and failures without capturing document text or user-entered form values.

## Sharing policy

A generic social-share button is not appropriate for every publication.

### Controlled or internal publications

- Share only an authenticated tenant link to an immutable revision and `DocumentLocation`.
- The recipient must pass normal authorization; possession of the URL grants no access.
- Optional expiry, named recipients and access logging may be applied.
- The link may include a selected quote only when policy permits.
- The file or page image must never be uploaded automatically to a third-party social platform.

### Uncontrolled drafts

- External/social sharing is disabled by default.
- Internal collaboration links retain the uncontrolled status and watermark.
- Download and print continue to apply formal uncontrolled markings.

### Public publications

- The Web Share API may be enabled only when Document Control marks the revision `PUBLIC_RELEASED`.
- Share the public canonical URL, title and approved summary; do not send private annotations.

### Restricted publications

- No external share action.
- Copy-link may be disabled or limited to named recipients.
- Every access and attempted share is auditable.

## Reader modes

1. **Standard mode:** title, control status, tabs, navigation and document.
2. **Reader mode:** full remaining viewport, document toolbar and optional navigation only; `Esc` exits.
3. **Audit mode:** document plus evidence tray, checklist/finding context and annotation tools.
4. **Compare mode:** two immutable revisions with synchronized locations.
5. **Presentation mode:** slides or selected pages; does not replace control status or watermark requirements.

## Accessibility requirements

- Complete keyboard operation.
- Visible focus and logical tab order.
- Screen-reader labels for page, sheet, slide and section location.
- Text mode for fixed-layout documents when dependable extracted text exists.
- High-contrast annotation patterns in addition to colour.
- Zoom up to at least 250% without horizontal trapping of controls.
- Reduced-motion support.

## Security and custody

- Source files and derivatives are checksum verified.
- PDF JavaScript, XFA and unsafe actions remain disabled unless a separately approved sandbox exists.
- HTML and Office-derived content is sanitized server-side.
- Form working copies are user- and revision-scoped.
- Annotation APIs enforce tenant, revision and visibility permissions.
- Controlled-record exports are immutable and include provenance.
- Reader telemetry excludes document contents, selected text and field values unless explicitly submitted as a controlled record.

## Delivery phases

### Phase 1 — stability and focused reading

- one-shot navigation commands;
- release stale TOC/search destinations on scroll and reflow;
- reader mode with `Esc` exit and fullscreen fallback;
- permission-controlled page links;
- exact-document browser regression for manual scroll after TOC and repeated fit changes.

### Phase 2 — canonical locations and private annotations

- `DocumentLocation` and `DocumentAnnotation` schemas;
- private multi-colour highlights and notes;
- PDF, semantic text and spreadsheet anchors;
- annotation list, filters and export.

### Phase 3 — audit evidence and team review

- evidence pinning into QMS/SMS workflows;
- team/audit visibility and comments;
- controlled evidence index and audit pack export;
- revision comparison and annotation migration review.

### Phase 4 — additional adapters and policy-based sharing

- DOCX/ODT, XLSX/ODS, PPTX/ODP, image/TIFF adapters;
- public-release Web Share support;
- named-recipient and expiring internal links;
- offline annotation synchronization.

## Mandatory test matrix

Every adapter and reader release must test:

- small, large and malformed documents;
- mixed page sizes and orientations;
- deep TOCs and internal links;
- manual scrolling after every navigation source;
- repeated fit/zoom and viewport resizing;
- entry and exit from reader mode using button and `Esc`;
- back/forward location handling;
- annotations before and after reflow;
- permission denial and cross-tenant isolation;
- controlled, uncontrolled, public and restricted sharing policies;
- keyboard and screen-reader operation;
- warm reopen and offline recovery;
- no blank/black rendered surfaces and no stale-navigation snap-back.
