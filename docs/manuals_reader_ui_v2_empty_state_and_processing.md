# Manuals Reader UI V2 — Empty State + Processing Hooks

## What was added
- A new action-oriented reader empty state hub in the center workspace with Upload, Run Processor, Run OCR, and View Logs actions.
- TOC empty-state action (`Generate outline`) to remove dead-end navigation when headings are missing.
- Right inspector tabs retained and refined for Revision, Acknowledgement, and Export actions.
- Sticky topbar refined into a single app-bar with grouped controls and explicit metadata warning chip.

## Backend hooks
- Added manuals processing endpoints:
  - `POST /manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/processing/run`
  - `POST /manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/ocr/run`
  - `GET /manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/processing/status`
  - `POST /manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/outline/generate`
- Endpoints currently enqueue/log audit events and return deterministic payloads to support frontend orchestration and future worker integration.

## UX behavior
- Workspace remains full-height (`100vh`) with independent scroll columns and no dead-space area.
- Empty states are action-oriented and compact, aligned with UI regression guidance.
- Reader keeps keyboard shortcuts for search and panel toggles.
