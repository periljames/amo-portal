# E-Sign Provider Integration (Phase 2)

## Provider modes
- `ESIGN_PROVIDER_MODE=appearance`
  - Uses `AppearanceOnlyProvider`.
  - `cryptographic_signature_applied=false`.
- `ESIGN_PROVIDER_MODE=external_pades`
  - Uses `ExternalPadesProvider` for sign + validate calls.
  - `cryptographic_signature_applied=true` only when provider returns a certificate-backed artifact.

## External provider config
- `ESIGN_EXTERNAL_SIGN_URL`
- `ESIGN_EXTERNAL_VALIDATE_URL`
- `ESIGN_EXTERNAL_TIMEOUT_SECONDS`
- `ESIGN_EXTERNAL_AUTH_MODE=none|bearer|mtls`
- `ESIGN_EXTERNAL_BEARER_TOKEN` (required when auth mode is bearer)
- `ESIGN_SIGNING_REASON_DEFAULT`
- `ESIGN_SIGNING_LOCATION_DEFAULT`
- `ESIGN_ENABLE_TIMESTAMPING`
- `ESIGN_REQUIRE_CRYPTO_PROVIDER_FOR_FINALIZATION`
- `ESIGN_PROVIDER_HEALTHCHECK_ON_STARTUP`
- `ESIGN_ALLOW_CRYPTO_FALLBACK_TO_APPEARANCE`

## Flow summary
1. WebAuthn assertion verifies signer approval and intent binding.
2. Signing service resolves provider mode.
3. Provider `sign_pdf` runs:
   - success -> signed artifact persisted with provider evidence fields.
   - failure -> hard-fail or fallback based on config.
4. Provider `validate_pdf` runs for crypto artifacts and stores validation summary/status.

## Provider event logging
`esign_provider_events` stores sanitized request/response/error metadata for:
- `SIGN_ATTEMPT`, `SIGN_SUCCESS`, `SIGN_FAILURE`
- `VALIDATE_ATTEMPT`, `VALIDATE_SUCCESS`, `VALIDATE_FAILURE`
- `HEALTHCHECK`

No secrets or bearer tokens are persisted.

## Audit semantics
Audit events include:
- `CRYPTO_SIGN_ATTEMPTED`, `CRYPTO_SIGN_SUCCEEDED`, `CRYPTO_SIGN_FAILED`
- `CRYPTO_VALIDATE_ATTEMPTED`, `CRYPTO_VALIDATE_SUCCEEDED`, `CRYPTO_VALIDATE_FAILED`
- `PROVIDER_HEALTHCHECK_RUN`
- `PROVIDER_FALLBACK_TO_APPEARANCE_ONLY`

## Release note
Phase 2 adds cryptographic provider integration path while preserving appearance-only fallback and strict output labeling.
