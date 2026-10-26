# Download and report review — 18 October 2026

The review covered frontend file-save handlers, Content-Disposition parsing, backend file/stream responses, report-job downloads and evidence-pack assembly. This is a source review across modules, with targeted automated and live checks; it is not a claim that every module was exercised live.

## Repairs

| Area | Fault | Result |
|---|---|---|
| Shared frontend downloads | Storage UUIDs appeared in filenames; truncation could discard extensions; Windows reserved names/control characters were not handled | Business labels survive, full UUID tokens (hyphenated or 32-character storage keys) are removed, extensions remain, filenames are safe for Windows |
| Filename headers | Multiple parsers handled UTF-8, malformed percent encoding and quoted filenames differently | Shared parser handles UTF-8/language tags, quoted names, missing headers and MIME extensions |
| Legacy backend downloads | Existing stored filenames could still expose full UUIDs through direct links | Streaming ASGI response guard normalizes UUID filenames, preserving disposition type, body, lengths and integrity headers |
| Training report jobs | Job UUID used as PDF/XLSX/CSV filename; frontend overrode server filename | Report code plus completion timestamp; browser honors server name |
| Training attendance/calendar | Event UUID used in exported name | Session title and scheduled date; calendar UID remains stable internally |
| QMS controlled documents | Storage basename returned as download name | Document code/title with issue and revision |
| Adopted audit reports | Storage basename copied into newly adopted governed revision filename | Audit reference and report revision |
| Reliability reports | Only internal report ID identified PDF output | Reporting period; controlled management outputs retain layout/period/snapshot number |
| DMS receipts | Circulation UUID in server and browser filename | Holding barcode, transaction type and timestamp; browser honors header |
| DMS evidence snapshots | Three UUIDs combined into JSON filename | Timestamped evidence filename; full identifiers stay inside the JSON |
| Evidence packs | Duplicate/case-equivalent attachment names could collide on extraction | Numbered suffixes preserve both attachments and their bytes |
| Other browser saves | Separate handlers bypassed shared filename rules | Shared sanitization applied across admin/user exports, procurement, training, reliability, document reports, EHM and evidence viewers |

Examples: `QMS-01-Maintenance Manual-issue-1-rev-2.pdf`, `training-compliance-summary-2026-10-18-123045.pdf`, `CAR-SAF-26-005-evidence-pack.zip`.

Storage paths, record identities, calendar UIDs, signed report content, source hashes and archive manifests retain their existing identifiers. This change does not migrate or regenerate historical signed artifacts. Archive directories and JSON manifests may contain record IDs for traceability.

## Verification

- 91 backend tests passed, covering filename rules, streaming response preservation, training job download metadata, distinct ZIP attachments, evidence exports, audit PDF rendering and archive governance, plus training operating/workflow contracts.
- 33 frontend tests passed, including six filename/save tests, including Unicode headers, malformed encoding, UUID-only names, extensions, Windows names and deferred URL cleanup.
- Production build passed, including TypeScript, 49 modal-source checks and the heavy-route import check. Existing large-chunk warnings remain.
- Live frontend CAR evidence-pack download produced `CAR-SAF-26-005-evidence-pack.zip`. The ZIP passed its CRC check, retained seven distinct entries and included the expected synthetic PDF.
- Live attachment download retained `SIMULATED_WORKFLOW_TEST_audit_notice.pdf`. Its SHA-256 matched the retained original; the downloaded file opened as a two-page PDF.
- `/livez` returned HTTP 200 after the final backend restart. `git diff --check` passed.

Live evidence: `.artifacts/audit-workflow-run/download-live-check.json`, `download-live-content-check.json`. Test/build logs: `download-backend-verified.log`, `download-frontend-final.log`, `download-build-final.log` in the same artifact directory.

## Limits

Only the existing simulated audit/CAR is used for live checks. No auditee response, report approval, issue, passkey signature or closure is performed. No independent claim is made about external mailbox delivery or every report template's visual layout.
