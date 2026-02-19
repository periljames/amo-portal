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
