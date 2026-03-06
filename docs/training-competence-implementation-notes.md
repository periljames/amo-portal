# Training & Competence Implementation Notes

## Delivered in this phase

- Added a multi-workspace Training & Competence module shell with ten operational sections:
  - Overview
  - Training Matrix
  - Schedule
  - Sessions
  - Attendance
  - Assessments
  - Certificates
  - Personnel Records
  - Templates
  - Admin / Settings
- Added certificates issuance/list backend endpoints using immutable `certificate_reference` on training records.
- Added a public verification API endpoint and public frontend verification page.
- Added attendance execution panel in module hub with participant status update action.

## New/updated route inventory

### Frontend
- `/maintenance/:amoCode/:department/training-competence`
- `/verify/certificate/:certificateNumber`

### Backend
- `GET /training/certificates`
- `POST /training/certificates/issue/{record_id}`
- `GET /public/certificates/verify/{certificate_number}`

## Constraints and assumptions

- Certificate generation currently issues immutable certificate numbers and verification metadata from record-backed source data.
- Full PDF template rendering, QR/barcode embedding, and supersede/revoke lifecycle remain follow-up increments.
- Existing entitlement and tenant scoping are preserved via current training router patterns.


## Additional hardening updates

- Added certificate issuance model migration: `aa11bb22cc33_add_training_certificate_issuance_tables.py`.
- Public verification now always returns JSON payloads (including malformed/not-found/unavailable states).
- Frontend verification helper now uses API base/proxy target safely in dev to avoid Vite `/public` static path conflicts.
- Module navigation updated to SectionList row pattern (mobile-first, no full-width stacked action buttons).

## Mobile UX overhaul updates

- Mobile top bar now renders a compact layout: hamburger (left), logo-only center, wifi icon-only live status (right).
- Mobile navigation uses drawer semantics (dialog role + aria-modal + scrim close) and does not rely on hover interactions.
- Training module uses row-based SectionList navigation with centered mobile content width and avoids full-width action slabs.
- Certificate detail drawer now provides compact icon actions (download, scan, open verify page).

## Scan flow

- Added scan-first route: `/verify/scan`.
- Scanner supports QR and barcode flows through:
  - native `BarcodeDetector` when available,
  - fallback `@zxing/browser` video decode when BarcodeDetector is unavailable.
- Hardware scanner keyboard-burst input is supported on `/verify/scan` and `/verify/certificate/:certificateNumber`.
- QR payload parser supports both raw certificate number and full verification URL payloads.


## UI correction pass (mobile/desktop)

- Removed overlapping header actions by moving mobile back navigation into a compact overflow menu in `QMSLayout` and keeping a single icon refresh action in-page.
- Mobile top bar now uses hamburger + logo-only glyph + compact wifi state icon, without tenant text blocks.
- Mobile drawer now includes an explicit close button, safe-area-aware sizing, and scrollable nav body to prevent clipped/cropped items.
- Training module now suppresses sample `TC-DEMO` certificate values outside sample mode and renders an explicit empty state when no real certificates are available.
- Certificate drawer actions remain compact icon controls and are wrapped to avoid overlap with long certificate numbers.
- Verification scan page updated to card-based UI and status row while preserving camera teardown and scanner fallbacks.
