# Procurement UI and API Review — 2026-08-03

## Implemented findings

- Replaced the oversized Procurement page with focused Command, Requests, Sourcing, Orders, Receiving, Suppliers, Quality Control and Documents work areas.
- Added partial-failure loading so one unavailable API does not blank the entire department.
- Added distinct high-contrast AOG, quarantine, restricted-supplier and Quality-hold warnings.
- Added accessible success, warning and error toasts with user-controlled audio cues.
- Added loading skeletons, refresh feedback, modal transitions and reduced-motion support.
- Added controlled drag-and-drop evidence capture with upload progress and recovery states.
- Added direct evidence attachment from requisitions, RFQs, quotations, purchase orders, receipts, suppliers and Quality holds.
- Added retained upload, physical-original registration, external-system reference and controlled DMS revision linkage.
- Added file size, extension, MIME, content-signature, path and duplicate SHA-256 controls.
- Added independent Quality verification, rejection and immutable void decisions.
- Removed Stores route aliases and kept Procurement and Stores as separate departments.
- Exposed canonical Procurement APIs through the existing authenticated tenant router.

## Validation

- Python source compilation
- Procurement module source-contract regressions
- Procurement document-control regressions
- Frontend strict TypeScript contract compilation
- Repository CI and production build required before merge
