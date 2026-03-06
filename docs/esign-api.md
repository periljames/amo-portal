## E-Signatures API (Phase 2)

Base prefix: `/api/v1/esign`

## WebAuthn
- `POST /webauthn/registration/options` (auth + entitlement)
- `POST /webauthn/registration/verify` (auth + entitlement)
- `POST /webauthn/assertion/options` (auth + entitlement)
- `POST /webauthn/assertion/verify` (auth + entitlement)

## Request lifecycle
- `POST /requests` (auth + entitlement)
- `POST /requests/{request_id}/send` (auth + entitlement)
- `GET /requests/{request_id}/signing-context` (auth signer + entitlement)

## Signing ceremony
- `POST /intents/{intent_id}/assertion/options` (auth signer + entitlement)
- `POST /intents/{intent_id}/assertion/verify-and-sign` (auth signer + entitlement)

## Token operations
- `POST /tokens/{token_id}/revoke` (auth + entitlement)

## Public verification
- `GET /verify/{token}`
- `GET /verify/{token}.json`

Verification response semantics:
- Invalid, expired, or revoked tokens all return `404 Not found` (no token existence leak).
- Successful responses include:
  - request title
  - signer metadata (masked email)
  - approval timestamps
  - document/artifact SHA-256
  - `appearance_applied`
  - `cryptographic_signature_applied` (`false` in Phase 1/1.1)

## Audit actions
- `DOC_VERSION_CREATED`
- `SIGNATURE_REQUEST_CREATED`
- `SIGNATURE_REQUEST_SENT`
- `SIGNING_INTENT_CREATED`
- `WEB_AUTHN_REG_OPTIONS_ISSUED`
- `WEB_AUTHN_REG_VERIFIED`
- `WEB_AUTHN_ASSERT_OPTIONS_ISSUED`
- `WEB_AUTHN_ASSERT_VERIFIED`
- `SIGNER_VIEWED`
- `SIGNER_APPROVED`
- `SIGNING_INTENT_APPROVAL_FAILED`
- `ARTIFACT_GENERATED`
- `REQUEST_COMPLETED`
- `TOKEN_CREATED`
- `VERIFY_TOKEN_REVOKED`
- `VERIFY_ENDPOINT_ACCESSED`


## Phase 2 routes
- `GET /artifacts/{artifact_id}/validation`
- `POST /artifacts/{artifact_id}/revalidate`
- `GET /provider/health`


## Phase 2.1 routes
- `POST /requests/{request_id}/evidence-bundle`
- `GET /evidence-bundles/{bundle_id}`
- `GET /evidence-bundles/{bundle_id}/download`
- `POST /requests/{request_id}/overrides`
- `GET /requests/{request_id}/overrides`
- `GET /provider/readiness`
- `POST /artifacts/{artifact_id}/revalidate-now`
- `GET /reports/trust-summary`


## Phase 3 frontend route integration
- Private UI pages mount under `/maintenance/:amoCode/:department/esign/*` and call the existing `/api/v1/esign/*` endpoints.
- Public verification UI route `/verify/:token` consumes `GET /api/v1/esign/verify/{token}.json`.


## Phase 3.1 routes
- `GET /artifacts/{artifact_id}/verify-link` (admin)
- `POST /artifacts/{artifact_id}/verify-link/regenerate` (admin)

## Phase 3.1 config
- `ESIGN_PUBLIC_VERIFY_BASE_URL`
- `ESIGN_PUBLIC_VERIFY_PATH_TEMPLATE`


## Phase 3.2 routes
- `GET /artifacts/{artifact_id}/access`
- `GET /artifacts/{artifact_id}/preview`
- `GET /artifacts/{artifact_id}/download`
- `POST /artifacts/{artifact_id}/compare-hash`
- `GET /verify/{token}/artifact-access`
- `GET /verify/{token}/download`
- `GET /verify/{token}/evidence-summary`
- `POST /verify/{token}/compare-hash`
