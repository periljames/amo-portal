# E-Sign Verify Link and QR Debugging (Phase 3.1)

## Verified token pipeline
1. Artifact finalization creates a verification token linked to `artifact_id`.
2. Public verify URL is built via trusted config (`ESIGN_PUBLIC_VERIFY_BASE_URL` + `ESIGN_PUBLIC_VERIFY_PATH_TEMPLATE`).
3. QR payload uses that URL (no PII/hashes embedded).
4. Public verify page resolves `/verify/:token` and calls backend `GET /api/v1/esign/verify/{token}.json`.

## Required config
- `ESIGN_PUBLIC_VERIFY_BASE_URL` (example: `https://portal.example.com`)
- `ESIGN_PUBLIC_VERIFY_PATH_TEMPLATE` (example: `/verify/{token}`)

## Operator debugging endpoints (private)
- `GET /api/v1/esign/artifacts/{id}/verify-link`
- `POST /api/v1/esign/artifacts/{id}/verify-link/regenerate`

These endpoints are tenant scoped and admin gated.

## Result semantics
- Invalid/expired/revoked token => generic `404 Not found` (non-enumerating)
- Valid token => verification payload
- Backend failure => transient error (service unavailable)

## Audit additions
- `VERIFY_TOKEN_CREATED_FOR_ARTIFACT`
- `VERIFY_QR_EMBED_ATTEMPTED`
- `VERIFY_QR_EMBED_SUCCEEDED`
- `VERIFY_QR_EMBED_FAILED`
- `VERIFY_LINK_REGENERATED`
