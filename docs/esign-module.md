# E-Signatures Module (Phase 1.1 Hardening, Backend)

## Step 0 discovery summary
- Backend framework: FastAPI with dependency-injected SQLAlchemy sessions from `amodb.database.get_db`, auth via JWT and `get_current_active_user`. Routes are mounted in `amodb.main`.
- Tenancy model: AMO tenant context (`amo_id`) is attached to authenticated users and used as tenant key on all private queries.
- Subscription gating: module access uses `amodb.entitlements.require_module("<MODULE_KEY>")` dependencies.
- Document storage pattern: existing modules store files using storage references (`storage_ref`/`storage_uri`) and persist SHA-256 separately.
- Audit trail pattern: append-only `audit_events` via `amodb.apps.audit.services.log_event`.

## Phase 1.1 hardening implemented
- Strict startup config validation for WebAuthn and token entropy.
- Challenge replay protection with challenge hash indexing and single-use consume-on-success.
- Assertion binding to signing intent/document hash and hash re-check before artifact generation.
- Public verification endpoint hardened to avoid token existence leak (`404` for invalid/expired/revoked).
- Token revocation endpoint added (tenant-scoped + audit logged).

## Configuration (validated on app startup)
- `ESIGN_WEBAUTHN_RP_ID` (string)
- `ESIGN_WEBAUTHN_EXPECTED_ORIGINS` (comma-separated list)
- `ESIGN_WEBAUTHN_REQUIRE_UV` (bool, default `true`)
- `ESIGN_CHALLENGE_TTL_SECONDS` (default `300`)
- `ESIGN_SIGNING_INTENT_TTL_SECONDS` (default `900`)
- `ESIGN_VERIFY_TOKEN_BYTES` (default `32`, i.e. 256-bit token entropy)

## Security guarantees (Phase 1/1.1)
- `content_sha256` is computed from exact stored source bytes.
- `intent_sha256` uses canonical JSON bytes (`sort_keys`, compact separators, UTF-8).
- Assertion options can be bound to intent/doc hash; verify-and-sign re-checks current source hash against committed intent hash.
- WebAuthn verification enforces expected origins, rpId, and UV policy.
- Challenges are single-use and expiring; consumed challenge replay is rejected.
- Verification tokens are opaque random strings with high entropy.
- Public verify responses do not expose tenant/internal ids.

## Non-guarantees (important)
- Phase 1/1.1 artifacts are **appearance-stamped** and integrity-verifiable, but **not cryptographically signed (no PAdES)**.
- `cryptographic_signature_applied` remains `false` unless a real cryptographic provider is implemented and validated.

## Operational smoke command
- `make esign_smoke`
  1. Runs Alembic upgrade to heads.
  2. Runs e-sign pytest suite.

## Release notes
- Phase 1.1 introduces hardening controls only; signing remains appearance-only.


## Phase 2 cryptographic provider path
- Adds external PAdES provider integration (`external_pades` mode) while preserving appearance-only fallback mode.
- Adds provider event evidence records and cryptographic validation status fields on artifacts.
- Public verify now reports storage integrity separately from cryptographic signature validation.


## Phase 2.1 trust/policy controls
- Adds signature policy model, policy-aware finalization, explicit fallback controls, and per-request overrides.
- Adds sanitized evidence bundle generation/download and trust summary reporting.
- Adds provider readiness evaluation and policy-driven revalidation behavior.
- Release note: silent downgrade is prevented; fallback must be policy/override authorized and auditable.


## Phase 3 frontend/operator integration
- Added tenant-scoped frontend pages under `/maintenance/:amoCode/:department/esign/*` for request creation, detail/revalidation, provider readiness, trust reporting, evidence bundles, and admin overrides.
- Added signer flow route `/maintenance/:amoCode/:department/esign/sign/:intentId` using browser-native WebAuthn passkey UX bound to backend intent endpoints.
- Added public verify route `/verify/:token` with non-leaky trust output and explicit labeling of approval vs storage integrity vs cryptographic validation.

## Phase 3.1 verify-link hardening
- QR/public verify URLs now use trusted config: `ESIGN_PUBLIC_VERIFY_BASE_URL` + `ESIGN_PUBLIC_VERIFY_PATH_TEMPLATE`.
- Added tenant-scoped admin endpoints to inspect/regenerate artifact verification links.
- Public verify continues generic 404 for invalid/expired/revoked tokens, with transient server errors treated separately by UI.


## Phase 3.2 artifact consumption and compare
- Added policy-aware private/public artifact access endpoints and UI controls for preview/download.
- Added hash compare flows (private and public token-scoped) to prove byte-level fingerprint matching.
- Verification result existence and artifact-access permission are intentionally separated in API/UI semantics.
