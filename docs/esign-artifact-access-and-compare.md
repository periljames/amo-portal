# E-Sign Artifact Access and Compare (Phase 3.2)

## Access semantics
- A valid verification record does **not** automatically grant artifact download.
- Access is policy-controlled separately for private and public contexts.
- Public invalid/revoked/expired tokens remain non-enumerating generic 404.

## Policy controls
- `allow_private_artifact_preview`
- `allow_private_artifact_download`
- `allow_public_artifact_access`
- `allow_public_artifact_download`
- `allow_public_evidence_summary_download`
- `watermark_public_downloads`
- `require_auth_for_original_artifact`

## Endpoints
Private:
- `GET /api/v1/esign/artifacts/{id}/access`
- `GET /api/v1/esign/artifacts/{id}/preview`
- `GET /api/v1/esign/artifacts/{id}/download`
- `POST /api/v1/esign/artifacts/{id}/compare-hash`

Public (token scoped):
- `GET /api/v1/esign/verify/{token}/artifact-access`
- `GET /api/v1/esign/verify/{token}/download`
- `GET /api/v1/esign/verify/{token}/evidence-summary`
- `POST /api/v1/esign/verify/{token}/compare-hash`

## Integrity and derivative rules
- Authoritative signed artifact remains immutable.
- Do not mutate crypto-signed originals for watermarking or public post-processing.
- If derivative/reference copies are introduced later, they must be separately stored and explicitly labeled.

## Compare flow
- Compare against authoritative signed artifact fingerprint using:
  - provided SHA-256, or
  - file content (encoded input)
- Result reports: expected hash, provided hash, and exact match boolean.
