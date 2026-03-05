# E-Sign Evidence Bundles (Phase 2.1)

## Purpose
Evidence bundles provide tenant-scoped, sanitized exports proving:
- required assurance policy,
- achieved assurance,
- fallback/override decisions,
- artifact + verification evidence.

## Endpoints
- `POST /api/v1/esign/requests/{id}/evidence-bundle`
- `GET /api/v1/esign/evidence-bundles/{bundle_id}`
- `GET /api/v1/esign/evidence-bundles/{bundle_id}/download`

## Bundle contents
ZIP includes deterministic JSON structures where practical:
- `manifest.json`
- `verification.json`
- `hashes.json`
- `signed-artifact.pdf` (when available)

Manifest includes policy summary, achieved level, signer summaries, hash references, provider-event summary, and WebAuthn intent hash references.

## Privacy / redaction
Bundles are sanitized exports, not raw internal dumps:
- no raw challenge values
- no bearer tokens
- no secret provider credentials
- masked signer email where applicable

## Audit trail
- `EVIDENCE_BUNDLE_GENERATED`
- `EVIDENCE_BUNDLE_DOWNLOADED`

## Operational note
Evidence bundles preserve labeling truth:
- appearance-only artifacts are not represented as cryptographically signed.
- storage hash validity and cryptographic validation are exported separately.
