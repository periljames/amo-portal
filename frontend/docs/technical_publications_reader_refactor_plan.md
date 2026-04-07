# Technical Publications Reader Refactor Plan (1View-style interaction model, AMO branding)

## 1) Component map
- `ReaderShell` (`ManualsReaderShell`) – compact operational header + 3-zone workspace shell
- `ReaderHeader` (inside shell) – global search + utility actions + collapse/fullscreen controls
- `PublicationTree` (left pane in `ManualReaderPage`) – make/library/manual/chapter/section/figure hierarchy
- `ReaderBreadcrumbs` (center) – active hierarchy breadcrumbs synchronized with route/section state
- `SectionReader` (center) – structured section rendering with previous/next traversal
- `FigureViewer` (center figure mode) – zoom/pan-like controls, figure metadata, section return path
- `SearchOverlay` (advanced search card) – filtered phrase + match mode exploration
- `HistoryPanel` (right contextual panel) – date-grouped recent route history
- `TaskPanel` (right contextual panel) – task tabs + print/email/pdf actions
- `OrderListPanel` (right contextual panel) – operational parts/material list controls
- `ChangeRequestDrawer` (right contextual panel) – context-prefilled PCR form
- `PublicationSelectorModal` (floating modal) – model/type/P/N/title filters + results table

## 2) Route map
Implemented deep-link support:
- `/t/:tenantSlug/publications/:manualId/:chapterId/:sectionId`
- `/t/:tenantSlug/publications/:manualId/:chapterId/:sectionId/:subSectionId`
- `/t/:tenantSlug/publications/:manualId/figure/:figureId`
- `/maintenance/:amoCode/publications/:manualId/:chapterId/:sectionId`
- `/maintenance/:amoCode/publications/:manualId/:chapterId/:sectionId/:subSectionId`
- `/maintenance/:amoCode/publications/:manualId/figure/:figureId`

Existing read route retained:
- `/.../manuals/:manualId/rev/:revId/read`

## 3) State model
Primary reader state:
- `active manual context`: tenant, manualId, revId, chapterId, sectionId, subSectionId, figureId
- `readerMode`: `section | figure | search | history | task | change-request`
- `context panel`: `metadata | search | history | task | change-request | figure | order-list`
- `activeSection`, `activeFigureId`
- pane visibility: `tocOpen`, `inspectorOpen`
- search: `search`, `advancedOpen`
- figure controls: `figureZoom`
- content presentation: `layout`, `zoom`
- history cache: `manuals.readerHistory` (localStorage)
- PCR context form model: manual metadata + location metadata + suggestion fields

## 4) Text wireframe
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Portal/Manual] [Global publication search................] [Utility icons]│
├─────────────────────────────────────────────────────────────────────────────┤
│ LEFT: PublicationTree        │ CENTER: Section/Figure Reader │ RIGHT Panel │
│ - Make                       │ - Breadcrumbs                 │ - Metadata  │
│   - Library                  │ - Manual meta chips           │ - Search    │
│     - Manual                 │ - Prev/Next section           │ - History   │
│       - Chapter              │ - Section content OR figure   │ - Task      │
│         - Section            │ - Open figure / Raise PCR     │ - OrderList │
│           - Figure nodes     │                               │ - PCR       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 5) Implementation phases
1. **Shell modernization**
   - compact dark utility header
   - action separators and collapsed-header mode
2. **Structured navigation + deep links**
   - hierarchy pane with active node synchronization
   - route updates for chapter/section/figure deep links
3. **Section/Figure reading workflow**
   - section reader with traversal
   - figure mode with contextual metadata and return path
4. **Operational utilities**
   - search/historical/task/order panels
   - PCR prefill drawer + publication selector modal
5. **Performance + accessibility hardening**
   - keyboard traversal, focus states, aria labels
   - lazy/virtualized large-manual rendering

## 6) UI copy (operator tone)
Header actions:
- `Notifications`, `Change Request`, `Manual Delta`, `Task`, `History`, `Order List`, `Support`, `Help`, `Home`, `Account`

Center actions:
- `Previous section`, `Next section`, `Advanced search`, `Open figure mode`, `Raise change request`

Figure mode:
- `Zoom out`, `Reset view`, `Zoom in`, `Fit width`, `Fit page`, `Previous figure`, `Next figure`, `Back to section`

Task panel:
- `Email`, `Print`, `Save as PDF`

Order list:
- `Open`, `Import`, `Save`, `Save as`, `Export TXT`, `Export PDF`

PCR:
- `Select Publication`, `Submit`

## 7) Backend data contract needed
Manual read payload (existing + required extensions):
- manual metadata: `id`, `code/part_number`, `manual_type`, `title`, `model`, `publication_date`, `revision_number`
- hierarchy nodes: chapter/section/sub-section with stable IDs and ordering
- section blocks with searchable text + html/xml
- figure references with IDs, captions, parent section/chapter, and optional parts/callouts
- search endpoints returning grouped hits and excerpts
- change request endpoint accepting contextual location metadata
- history event payloads (or rely on client event persistence)

## 8) Endpoints to add/change
Add/extend:
- `GET /manuals/.../tree` (hierarchy: make→library→manual→chapter→section→figure)
- `GET /manuals/.../search` (grouped quick search)
- `POST /manuals/.../search/advanced`
- `GET /manuals/.../figures/:figureId`
- `POST /quality/pcr` (contextual publication change request)
- `GET /manuals/publication-selector` (filters: model/type/pn/title)

Keep existing:
- `GET /manuals/.../read`
- `GET /manuals/.../workflow`
- `GET /manuals/.../diff`

## 9) Risks + fallback for PDF-only manuals
Risks:
- Missing structural metadata in PDF-only sources
- Inconsistent figure extraction/captions
- Large manuals causing render jank

Fallback model:
- build synthetic TOC index from outline/OCR anchors
- map section nodes to PDF page ranges
- use figure extraction sidecar table for page-bound figures
- keep reader state independent from raw file rendering

## 10) React/TypeScript implementation alignment
Current implementation updates:
- shell + header utilities upgraded in `packages/manuals-reader/shell.tsx`
- deep routes added in `packages/manuals-reader/routes.tsx`
- reader state/workflow expanded in `pages/manuals/ManualReaderPage.tsx`
- operational styling refined in `pages/manuals/manualReader.css`

Next increments:
- split `ManualReaderPage` into modular components listed above
- replace mock selector/task/order data with API-backed hooks
- add optimistic PCR submit + attachment handling
- add section/figure URL synchronization guards
