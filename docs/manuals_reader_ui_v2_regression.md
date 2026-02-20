# Manuals Reader UI V2 — Objective Regression Notes

## Design objectives checked
- Single sticky branded topbar (no stacked header rows).
- Left/center/right workstation hierarchy.
- Reader supports Focus mode + Fullscreen API.
- Layout modes: continuous, paged 1-up/2-up/3-up.
- Responsive fallback to one-column reader on narrow widths.
- Token-driven surfaces (`--paper`, `--ink`, `--tenant-bg`) and tenant accent usage.

## Route compatibility
- Existing manuals routes preserved.
- Added deterministic viewer route:
  - `/maintenance/:amoCode/:department/qms/documents/:docId/revisions/:revId/view`

## Realtime behavior
- Reader subscribes to `/api/events`.
- Supports `lastEventId` replay query and `reset` event handling.
- Applies targeted data refresh (read/workflow/diff) for manual-related events.

## Controlled export constraints
- Uncontrolled watermark defaults ON.
- Only authorized roles can disable watermark or issue controlled hard copies.
- Controlled mode forces watermark OFF.

## Known implementation caveat
- Paged mode currently uses virtualized page cards and not full Paged.js pagination fragments yet.


## Header/spacing fixes in this pass
- Removed stacked status rows and moved status chip to single app bar.
- Replaced malformed placeholders (`- -`) with metadata warning chip + missing fields tooltip.
- Ensured workspace consumes `calc(100vh - header)` with independent panel/viewer scrolling (`min-h-0` behavior).
- Added inspector tabs, loading skeletons, and explicit empty states for TOC/viewer.

- Added empty-state and processing/OCR hook implementation notes in `docs/manuals_reader_ui_v2_empty_state_and_processing.md`.
